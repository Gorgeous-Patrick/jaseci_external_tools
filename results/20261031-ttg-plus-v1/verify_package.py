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
            acceptance=metadata['diagnostic-acceptance.json'];assert acceptance['passed'] and acceptance['full_native_oracles']
        print('Verified '+archive['package_path'],flush=True)
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
        entry=by_original[original];assert 'archive_member' not in entry
        return json.loads(checked(root,entry['package_path']).read_text())
    base='project-notes/measurements/ttg-plus-performance-20261031/'
    for name,count,category in [('formal-v1',36,'formal36'),('correctness-v5',9,'correctness9')]:
        index=mapped_json(base+name+'/index.json');assert index['passed'] and index['status']=='complete' and len(index['rows'])==count
        assert sum(a['package_path'].startswith('raw/'+category+'/') for a in archives)==count
        for row in index['rows']:
            assert row['passed']
            for ref in row['result'].values():
                if isinstance(ref,dict) and 'path' in ref and 'sha256' in ref:resolve(ref)
            original=row['result']['raw']['path'].removeprefix(prefix)
            assert seals[original]['original_seal_sha256']==row['result']['raw']['sha256']
        if name=='formal-v1':
            assert Counter(r['phase'] for r in index['rows'])=={'measured':27,'excluded_warmup':9}
            assert Counter((r['case_id'],r['config_id']) for r in index['rows'])=={(case,cell):4 for case in ('linked_list32','linked_list1000','littlex') for cell in ('off','prefusion','ttg_plus')}
    assert len(archives)==47 and sum(a['package_path'].startswith('raw/diagnostics2/') for a in archives)==2
    closure=json.loads((root/'manifests/source-closure.json').read_text());assert len(closure)==50
    for r in closure:assert by_original[r['original']]['sha256']==r['sha256']
    manifest=mapped_json('reproduction/ttg-app-performance/suite-final-20261030-v1/snapshot.json')
    assert len(manifest['files'])==90
    for name,h in manifest['files'].items():assert by_original['reproduction/ttg-app-performance/suite-final-20261030-v1/'+name]['sha256']==h
    required=json.loads((root/'manifests/required-references.json').read_text())
    for ref in required:resolve(ref)
    pdf=root/'report/ttg-plus-performance.pdf'
    assert sha(pdf)=='3f3138080d751e6953df74715c10176b22e79627e8d9a27449055fc90430378b'
    assert len(list(root.rglob('*.pdf')))==1,'Duplicate report PDF'
    print(json.dumps(dict(passed=True,package_files=len(actual),archives_verified=47,formal_captured=36,
        primary_samples=27,excluded_warmups=9,correctness_cases=9,diagnostic_cases=2,
        execution_sources=50,app_sources=90,mapped_paths=len(mapping),required_refs=len(required),
        scope='Portable bytes/seals/decoded representations/selection/source/reference verification; no DB or experiment'),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path);parser.add_argument('--original-root',type=Path)
    args=parser.parse_args();verify((args.root or Path(__file__).resolve().parent).resolve(),args.original_root.resolve() if args.original_root else None)
