"""Read-only byte identity proof binding41260 SQL controls to final866222."""
import argparse
import json
from pathlib import Path
from evidence import sha256,read_json,verify_case
from validate_preparation import EVIDENCE,OWN

COMPONENTS=('jac/jaclang/data/pgwire.jac','jac/jaclang/data/impl/pgwire.impl.jac',
    'jac/jaclang/data/store.jac','jac/jaclang/data/impl/store.impl.jac',
    'jac/jaclang/data/pgload.py','jac/jaclang/data/pgpool.jac',
    'jac/jaclang/runtime/ttg_process_reader.jac','jac/jaclang/runtime/prefetch.jac',
    'jac/jaclang/runtime/ttg_prefetch_model.jac')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('predecessor-clean','predecessor-direct','final-clean','final-direct','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(EVIDENCE) or output==EVIDENCE:raise ValueError('New owned output required')
    output.mkdir(parents=True,exist_ok=False)
    manifests={key:read_json(getattr(args,key)) for key in ('predecessor_clean','predecessor_direct','final_clean','final_direct')}
    comparisons=[]
    for pair in (('predecessor_clean','final_clean'),('predecessor_direct','final_direct')):
        a,b=(manifests[name] for name in pair)
        names=[*COMPONENTS]
        if pair[0].endswith('direct'):names.append('jac/continuation_probe.py')
        for name in names:
            first=Path(a['root'])/name;last=Path(b['root'])/name
            ah=sha256(first);bh=sha256(last)
            if ah!=a['files'][name] or bh!=b['files'][name]:raise ValueError('Component source mutation')
            comparisons.append(dict(pair=list(pair),file=name,sha256=ah,equal=ah==bh))
    patches=[m['patch']['sha256'] for key,m in manifests.items() if key.endswith('direct')]
    if len(set(patches))!=1:raise ValueError('Effective observer patch changed')
    if not all(c['equal'] for c in comparisons):raise ValueError('Component byte difference; cannot transfer validation')
    raw=EVIDENCE/'overhead-41260-v1'
    capture=EVIDENCE/'sql-41260-v3'
    control_seal=verify_case(raw)
    capture_seal=verify_case(capture,allow_failed=True)
    supplemental=EVIDENCE/'sql-41260-v3-supplement-v1/result.json'
    result=dict(passed=True,kind='final_runtime_calibrated_component_byte_binding',formal_application_samples=0,
        predecessor_commit=manifests['predecessor_clean']['commit'],final_commit=manifests['final_clean']['commit'],
        manifests={key:dict(path=str(getattr(args,key).resolve()),sha256=sha256(getattr(args,key))) for key in manifests},
        comparisons=comparisons,patch_sha256=patches[0],overhead_input_seal=control_seal,
        SQL_capture_original_failed_seal=capture_seal,supplemental_SQL_validation=dict(path=str(supplemental),sha256=sha256(supplemental)),
        definition='Exact unchanged clean+effective PgWire/store/reader/dispatch/model components and direct observer sink; controls are component evidence, not whole-runtime/application performance acceptance',
        HTTP_observer_note='Nested scope ID, explicit profile reset and weakref Session-nonce metadata added after SQL-only controls; these modules were not executed by the SQL controls. Final application correctness independently verifies their path.',
        builder=dict(path=str(Path(__file__).resolve()),sha256=sha256(__file__)))
    (output/'binding.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'artifacts.json').write_text(json.dumps(dict(passed=True,files={'binding.json':sha256(output/'binding.json')}),indent=2)+'\n')
    print(json.dumps(dict(output=str(output),equal_components=len(comparisons),passed=True)))


if __name__=='__main__':main()
