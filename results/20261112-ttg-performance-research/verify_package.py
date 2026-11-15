#!/usr/bin/env python3
"""Portable byte/seal/decoded-representation/index verifier; no experiment jobs."""
import argparse
from collections import Counter
import hashlib
import gzip
import json
from pathlib import Path
import tarfile


def sha_stream(stream):
    value=hashlib.sha256()
    for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def sha(path):
    with path.open('rb') as stream:return sha_stream(stream)


def checked(root,name):
    path=Path(name)
    assert not path.is_absolute() and '..' not in path.parts,name
    return root/path


def verify(root,original_root=None):
    integrity=json.loads((root/'package-integrity.json').read_text());assert integrity['passed']
    for name,h in integrity['manifest_hashes'].items():assert sha(checked(root,name))==h,name
    inventory=json.loads((root/'manifests/files.json').read_text());names={r['path'] for r in inventory}
    assert len(names)==len(inventory)
    excluded={'manifests/files.json','package-integrity.json','SHA256SUMS'}
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    assert actual==names|excluded,'Unknown or missing package files'
    assert not any(p.is_symlink() for p in root.rglob('*'))
    for r in inventory:
        p=checked(root,r['path']);assert p.stat().st_size==r['bytes']<100_000_000,r['path']
        assert sha(p)==r['sha256'],r['path']
    archives=json.loads((root/'manifests/archive-members.json').read_text());members={};seals={}
    for archive in archives:
        path=checked(root,archive['package_path']);assert sha(path)==archive['sha256']
        declared={r['member']:r for r in archive['members']};assert len(declared)==len(archive['members'])
        original_names=[str(Path(r['original']).relative_to(Path(archive['original_seal']).parent)) for r in declared.values()]
        assert len(original_names)==len(set(original_names))
        seen=set();metadata={}
        with tarfile.open(path,'r|xz') as tar:
            for info in tar:
                assert info.isfile() and info.name in declared and info.name not in seen,info.name
                r=declared[info.name];assert info.size==r['bytes'];stream=tar.extractfile(info)
                if info.name in ('artifacts.json','compression.json','diagnostic-acceptance.json'):
                    data=stream.read();assert hashlib.sha256(data).hexdigest()==r['sha256'];metadata[info.name]=json.loads(data)
                else:assert sha_stream(stream)==r['sha256'],info.name
                seen.add(info.name);members[(archive['package_path'],info.name)]=r
        assert seen==set(declared),'Unknown/duplicate/missing archive member'
        seal=metadata['artifacts.json'];assert seal['passed'] is True
        assert declared['artifacts.json']['sha256']==archive['original_seal_sha256']
        assert set(original_names)==set(seal['files'])|{'artifacts.json'}
        compression={r['sealed_name']:r for r in metadata.get('compression.json',[])}
        for name,r in declared.items():
            original=str(Path(r['original']).relative_to(Path(archive['original_seal']).parent))
            expected=archive['original_seal_sha256'] if original=='artifacts.json' else seal['files'][original]
            assert r['original_sha256']==expected
            if 'representation' in r:
                rep=r['representation'];assert rep['kind']=='gzip_to_decoded_tar_xz'
                assert original in compression
                entry=compression[original]
                assert entry==rep['compression_entry'],'Representation differs from original compression document'
                assert entry['gzip_sha256']==expected==rep['original_gzip_sha256']
                assert entry['compressed_bytes']==rep['original_gzip_bytes']
                assert entry['uncompressed_sha256']==r['sha256'] and entry['uncompressed_bytes']==r['bytes']
                assert entry['raw_name']==name and entry['sealed_name']==original
                if original_root is not None:
                    source=checked(original_root,r['original']);assert sha(source)==expected
                    h=hashlib.sha256();count=0
                    with gzip.open(source,'rb') as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block);count+=len(block)
                    assert count==r['bytes'] and h.hexdigest()==r['sha256'], 'Original full gzip decode differs'
                assert rep['compression_document_sha256']==declared['compression.json']['sha256']
                assert name==original.removesuffix('.gz') and rep['compressed_bytes_identical'] is False
                assert rep['decoded_bytes_identical'] is True
            else:assert r['sha256']==expected
        seals[archive['original_seal']]=archive
        if archive['package_path'].startswith('raw/diagnostics2/'):
            acceptance=metadata['diagnostic-acceptance.json'];assert acceptance['passed'] and acceptance['full_workflow_oracle_passed'] and acceptance['actual_call']['returned_rows']==1000
        print('Verified '+archive['package_path'],flush=True)
    large=json.loads((root/'manifests/large-metadata.json').read_text());large_bytes={}
    assert sha(checked(root,large['package_path']))==large['sha256']
    expected_large={r['member']:r for r in large['members']};seen_large=set()
    with tarfile.open(checked(root,large['package_path']),'r|xz') as tar:
        for info in tar:
            assert info.isfile() and info.name in expected_large and info.name not in seen_large
            r=expected_large[info.name];data=tar.extractfile(info).read()
            assert len(data)==r['bytes'] and hashlib.sha256(data).hexdigest()==r['sha256']
            large_bytes[info.name]=data
            members[(large['package_path'],info.name)]={'original_sha256':r['sha256'],'sha256':r['sha256']}
            seen_large.add(info.name)
    assert seen_large==set(expected_large)
    mapping=json.loads((root/'manifests/path-mapping.json').read_text());by_original={r['original']:r for r in mapping}
    assert len(by_original)==len(mapping)
    for entry in mapping:
        if 'archive_member' in entry:
            member=members[(entry['package_path'],entry['archive_member'])]
            assert member['original_sha256']==entry['sha256']
            if 'representation' in entry:
                assert entry['representation']==member['representation'] and entry['decoded_sha256']==member['sha256']
            else:assert member['sha256']==entry['sha256']
        else:assert sha(checked(root,entry['package_path']))==entry['sha256']
    prefix='/home/baichuan/jaseci/'
    def resolve(ref):
        original=ref['path'].removeprefix(prefix);entry=by_original[original]
        assert entry['sha256']==ref['sha256'],original
        return entry
    def mapped_json(original):
        entry=by_original[original]
        if 'archive_member' not in entry:return json.loads(checked(root,entry['package_path']).read_text())
        if entry['package_path']==large['package_path']:return json.loads(large_bytes[entry['archive_member']])
        with tarfile.open(checked(root,entry['package_path']),'r:xz') as tar:
            return json.loads(tar.extractfile(entry['archive_member']).read())
    cases=json.loads((root/'manifests/case-inventory.json').read_text())
    assert len(cases)==len({c['trial_id'] for c in cases})==len(archives)==464
    assert Counter(c['category'] for c in cases)=={'first-v1':45,'small-rest-v1':210,'larger-v1':31,'extend-n5-v2':114,'precision-v2':57,'CPU-diagnostic':6,'failed-preserved':1}
    for case in cases:
        resolve(case['original_raw'])
        original=case['original_raw']['path'].removeprefix(prefix)
        assert seals[original]['original_seal_sha256']==case['original_raw']['sha256']
    base='project-notes/measurements/ttg-performance-research-20261112/'
    for stage,count in [('first-v1',45),('small-rest-v1',210),('larger-v1',31),('extend-n5-v2',114),('precision-v2',57)]:
        index=mapped_json(base+stage+'/index.json');assert len(index['rows'])==count
        assert (index['passed'] and index['status']=='complete') or (stage=='larger-v1' and index['status']=='failed')
        for row in index['rows']:
            assert row['passed']
            for value in row['result'].values():
                if isinstance(value,dict) and 'path' in value and 'sha256' in value:resolve(value)
            resolve(row['gil_proof'])
    primary=mapped_json(base+'export-n5-v2/results.json')
    assert primary['passed'] and primary['counts']=={'captured':399,'correctness':57,'excluded_warmups':57,'measured':285,'measured_cells':57}
    assert len(primary['rows'])==57 and all(r['n']==5 for r in primary['rows']) and len(primary['inventory'])==60
    assert Counter(r['status'] for r in primary['inventory'])=={'completed_n5':57,'correctness_only':1,'failed_isolation_gate':1,'not_run_after_first_failure':1}
    precision=mapped_json(base+'export-precision-v2/results.json');assert precision['passed'] and len(precision['samples'])==57
    assert all(r['n']==1 for r in precision['samples'])
    source=json.loads((root/'manifests/source-closure.json').read_text());assert len(source)==11640
    for r in source:
        if 'package_path' in r:assert by_original[r['original']]['sha256']==r['sha256']
        else:assert r['provider'].startswith('Pinned runtime commit')
    required=json.loads((root/'manifests/required-references.json').read_text())
    for value in required:resolve(value)
    assert sha(root/'report/ttg-performance-research.pdf')==integrity['report_sha256']=='717299c5cad5c6f26c825ffe5cc27252a557d3b528167d9b066ee47a82b6d690'
    assert len(list(root.rglob('*.pdf')))==1
    print(json.dumps(dict(passed=True,files=len(actual),case_archives=464,archive_members=len(members),comparison_records=399,primary_measured=285,precision_n1=57,CPU_diagnostic_workflows=6,terminal_LL_correctness_extra=1,failed_extra=1,source_manifest_entries=11640,mapped_paths=len(mapping),required_references=len(required),scope='Portable package bytes, archive seals/decoded representations, case selection, reference/source mapping; no DB or runtime experiment'),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path);p.add_argument('--original-root',type=Path);a=p.parse_args()
    verify((a.root or Path(__file__).resolve().parent).resolve(),a.original_root.resolve() if a.original_root else None)
