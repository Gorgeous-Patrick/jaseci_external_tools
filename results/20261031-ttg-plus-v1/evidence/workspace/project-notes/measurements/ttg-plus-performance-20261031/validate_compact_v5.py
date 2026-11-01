"""One read-only recorded large rederive; no runtime, service or DB execution."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path('/home/baichuan/jaseci');OWN=ROOT/'reproduction/ttg-plus-performance'
E=ROOT/'project-notes/measurements/ttg-plus-performance-20261031'
sys.path.insert(0,str(OWN))
from interop import read_json,checked_ref,reference,require
from plus_metrics import summarize
from review import check_sources


def small_legacy_sections(archive,expected):
    """Skip only the known top-level model_outcomes value, without decoding it.

    Fixed markers come from the frozen pretty-JSON writer. Prefix/tail are
    bounded16MiB; the full decoded-byte SHA still validates the historical file.
    """
    start=b'\n  "model_outcomes":';end=b'\n  "profile_reset_events":'
    phase='prefix';prefix=b'';tail=b'';window=b'';digest=hashlib.sha256();size=0
    with gzip.open(archive,'rb') as source:
        for chunk in iter(lambda:source.read(65536),b''):
            digest.update(chunk);size+=len(chunk)
            if phase=='prefix':
                prefix+=chunk;require(len(prefix)<=16*1024**2,'Legacy header exceeds bound')
                offset=prefix.find(start)
                if offset<0:continue
                data=prefix[offset+len(start):];prefix=prefix[:offset];phase='skip'
            elif phase=='skip':data=window+chunk
            else:
                tail+=chunk;require(len(tail)<=16*1024**2,'Legacy tail exceeds bound');continue
            offset=data.find(end)
            if offset>=0:tail=data[offset:];phase='tail'
            else:window=data[-len(end):]
    require(phase=='tail' and digest.hexdigest()==expected['decoded_sha256'] and
        size==expected['decoded_bytes'],'Historical archive decoded content differs')
    return json.loads(prefix+tail),dict(decoded_bytes=size,decoded_sha256=digest.hexdigest(),
        parsed_bytes=len(prefix)+len(tail),skipped_key='model_outcomes')


def main():
    check_sources(E/'runner-candidate-v5/sources.json')
    out=E/'large-derived-validation-v1';require(not out.exists(),'NEW validation directory required');out.mkdir()
    index=read_json(E/'correctness-v4/index.json')
    row=next(r for r in index['rows'] if r['case_id']=='linked_list1000' and r['config_id']=='prefusion')
    relocation_path=ROOT/'project-notes/measurements/ttg-plus-acl-20261031/historical-v4-metric-archive-v1/manifest.json'
    relocation=read_json(relocation_path);require(relocation['passed'],'Verified historical relocation required')
    require(relocation['historical_accepted_metric_ref']==row['result']['metrics'],'Archive/index metric identity differs')
    archive=checked_ref(relocation['archive'],relocation_path.parent)
    before,legacy_read=small_legacy_sections(archive,relocation['archive'])
    print(json.dumps(dict(stage='legacy_scalar_sections_verified',**legacy_read)),flush=True)
    started=time.monotonic();directory=Path(row['result']['raw']['path']).parent
    actual=summarize(directory,Path(row['result']['acceptance']['path']))
    shared={k:v for k,v in actual.items() if k not in ('model_outcomes','model_outcome_format')}
    require(shared==before,'Recorded large primary/count/scope/fingerprint fields differ')
    path=out/'compact-metric.json';path.write_text(json.dumps(actual,indent=2)+'\n')
    print(json.dumps(dict(stage='large_compact_metric_verified',bytes=path.stat().st_size,
        seconds=time.monotonic()-started)),flush=True)
    # Validate exact raw record references and record sizes without parsing or
    # serializing the native payload a second time.
    wanted={}
    for event in actual['model_outcomes']:
        wanted.setdefault(event['raw_event']['path'],{})[event['raw_event']['line']]=event
    footprints=[]
    for name,numbers in wanted.items():
        file_path=Path(name)
        with gzip.open(file_path,'rb') if file_path.suffix=='.gz' else file_path.open('rb') as source:
            for number,line in enumerate(source,1):
                if number in numbers:
                    event=numbers[number];require(hashlib.sha256(line).hexdigest()==event['raw_event']['record_sha256'],
                        'Compact raw record reference differs')
                    summary=event['summary']
                    footprints.append(dict(request=event['origin_request_id'],scope_id=event['scope_id'],
                        raw_record_bytes=len(line),**{key:summary[key] for key in
                        ('plan_count','continuation_count','continuation_path_count','continuation_execution_count',
                         'submitted_count','promoted_count','region_count')}))
                del line
    require(len(footprints)==len(actual['model_outcomes']),'Incomplete raw reference audit')
    result=dict(passed=True,scope='Read-only rederive from historical accepted correctness raw; no new workload/formal sample',
        source=reference(Path(__file__).resolve()),sources=reference(E/'runner-candidate-v5/sources.json'),
        original_index=reference(E/'correctness-v4/index.json'),historical_metric=row['result']['metrics'],
        relocation=reference(relocation_path),legacy_reader=legacy_read,raw=row['result']['raw'],
        acceptance=row['result']['acceptance'],compact_metric=reference(path),compact_bytes=path.stat().st_size,
        original_bytes=relocation['archive']['decoded_bytes'],all_non_model_fields_exactly_equal=True,
        compared_fields=list(before),native_outcome_footprints=footprints,
        full_native_raw_unchanged=True,raw_reference_hashes_verified=True,formal_samples=0)
    proof=out/'validation.json';proof.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(proof=reference(proof),passed=True,compact_bytes=result['compact_bytes'],
        native_outcomes=len(footprints),all_non_model_fields_equal=True)),flush=True)


if __name__=='__main__':main()
