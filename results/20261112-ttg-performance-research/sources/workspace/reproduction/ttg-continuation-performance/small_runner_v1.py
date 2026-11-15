"""EXACT LittleX+IssueDesk x6 x(1 excluded warmup+3 measured) formal runner.

Uses gate.AUTHORIZATION only; no alternate approval path or correctness reuse.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from dataclasses import replace
import json
from pathlib import Path
import re
import shutil
import gate
from gate import CONFIGURATIONS
from evidence import read_json, sha256, checked_ref, verify_case
from application_matrix_v2 import source_hashes as base_sources
from app_tier_adapter import Applications, OLD_SUITE
from owned_postgres_v2 import OwnedPostgres
from small_metrics_v1 import summarize
from validate_preparation import OWN, EVIDENCE

APPS = ('littlex', 'issue_desk')
CASES = tuple('apps/'+app for app in APPS)
NEW_FILES = ('small_runner_v1.py', 'small_metrics_v1.py', 'small_export_v1.py',
             'build_small_review_v1.py', 'test_small_v1.py')


def sources():
    return {**base_sources(), **{str(OWN/name):sha256(OWN/name) for name in NEW_FILES}}


def schedule():
    rows = []
    ids = [c[0] for c in CONFIGURATIONS]
    for ai, app in enumerate(APPS):
        for repeat in range(4):
            shift = (ai+repeat) % 6
            order = ids[shift:]+ids[:shift]
            if (ai+repeat) % 2:
                order = list(reversed(order))
            for config in order:
                phase = 'excluded_warmup' if repeat == 0 else 'measured'
                rows.append(dict(app=app, config_id=config, phase=phase, repeat=repeat-1,
                                 trial_id=f'{app}-{config}-{phase}-{repeat-1}'))
    return rows


def complete_preflight(path):
    value = read_json(path)
    expected = {(app, c[0]) for app in value['selected_apps'] for c in CONFIGURATIONS}
    rows = value['cases']
    actual = [(r['app'], r['config_id']) for r in rows]
    gate.require(len(value['selected_apps']) == 30 and len(set(value['selected_apps'])) == 30,
                 'Full original30 correctness inventory required')
    gate.require(value.get('status') == 'complete' and value.get('passed') is True and
                 value.get('formal_samples') == 0 and len(actual) == 180 and
                 len(set(actual)) == 180 and set(actual) == expected,
                 'NEW full180 correctness has not passed')
    gate.require(all(r.get('passed') is True and r['proof'].get('passed') is True and
                 all(r['proof']['checks'].get(k) is True for k in ('native','oracle','fresh_session','restart'))
                 for r in rows), 'Failed full180 correctness case')
    return value


def validate_release():
    release = gate.validate()  # fixed MAIN-ONLY authorization; no CLI override
    gate.require(release.selected_cases == CASES and release.plan['case_ids'] == list(CASES),
                 'Release must select ONLY LittleX and IssueDesk, in declared order')
    plan = release.plan
    gate.require(plan['measured_repeats'] == 3 and plan['excluded_warmups'] == 1 and
                 plan['seeds'] == [42] and plan.get('schedule') == schedule(), 'Wrong 48-trial subset plan')
    gate.require(plan.get('primary_phase') == 'workflow' and plan.get('steady_reads_are_replicates') is False,
                 'Business workflow and independent workflow repeats required')
    instrument = read_json(release.instrument_path)
    gate.require(instrument['sources'] == sources(), 'Exact small runner/numeric closure differs')
    index_path = checked_ref(plan['complete_180_preflight'], release.plan_path.parent)
    complete_preflight(index_path)
    gate.require(plan.get('preflight_complete') is True, 'Draft/incomplete preflight plan cannot be released')
    return replace(release,source_refs=release.source_refs+((str(index_path),sha256(index_path)),))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n')


class SmallPostgres(OwnedPostgres):
    """Validate measured raw intervals BEFORE the reviewed natural DROP."""
    def sql(self, statement, database='postgres'):
        if statement.startswith('DROP DATABASE '):
            context = self.cleanup_context
            directory = Path(context['case_directory'])
            acceptance = Path(context['acceptance_directory'])/(directory.name+'.json')
            metrics = summarize(directory, acceptance)
            destination = self.metrics_directory/(directory.name+'.json')
            gate.require(not destination.exists(), 'Trial metric proof already exists')
            write(destination, metrics)
            gate.revalidate(self.release)
        return super().sql(statement, database)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('formal',))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cluster', type=Path, required=True)
    args = parser.parse_args()
    release = validate_release()
    output = args.output.resolve()
    gate.require(output.is_relative_to(EVIDENCE) and output != EVIDENCE, 'New owned output required')
    gate.require(str(output)==release.plan['planned_output'] and
                 str(args.cluster.resolve())==release.plan['planned_cluster'], 'Output/cluster differ from released plan')
    gate.require(not output.exists() and not args.cluster.exists(), 'No carry/reuse of trial or cluster')
    output.mkdir(parents=True)
    metric_dir = output/'metrics'; metric_dir.mkdir()
    source_dir = output/'execution-sources'; source_dir.mkdir()
    closure = sources()
    for i, (path, expected) in enumerate(closure.items()):
        target = source_dir/f'{i:02d}-{Path(path).name}'
        shutil.copy2(path, target)
        gate.require(sha256(target) == expected, 'Source mutation during copy')
    authorization = read_json(release.authorization_path)
    review_path = checked_ref(authorization['artifacts']['main_review'], release.authorization_path.parent)
    cleanup_review = dict(path=str(review_path), sha256=sha256(review_path))
    cleanup_manifests = dict(runtime=dict(path=str(release.runtime_manifest),sha256=sha256(release.runtime_manifest)),
        overlay=dict(path=str(release.overlay_manifest),sha256=sha256(release.overlay_manifest)),
        suite=dict(path=str(OLD_SUITE),sha256=sha256(OLD_SUITE)))
    review = read_json(review_path)
    gate.require(review.get('purpose') == 'cleanup_gate_v2_review' and review.get('sources') == closure and
                 review.get('source_manifests') == cleanup_manifests,
                 'Main formal review must also accept exact reused cleanup closure/source manifests')
    correctness = read_json(release.correctness_path)
    baselines = {r['case_id'].split('/')[1]:read_json(checked_ref(r['evidence'],release.correctness_path.parent))
                 for r in correctness['cases'] if r['config_id']=='none'}
    suite = Applications()
    index = dict(kind='partial_two_app_primary_DB_experiment',status='running',passed=False,
        authorization=dict(path=str(release.authorization_path),sha256=release.authorization_sha256),
        plan=dict(path=str(release.plan_path),sha256=sha256(release.plan_path)),
        sources=closure, complete_180_preflight=release.plan['complete_180_preflight'],
        expected_schedule=schedule(),cases=[], started_utc=datetime.now(timezone.utc).isoformat(),
        primary_phase='workflow',warmup_workflows_excluded=12,measured_workflows_expected=36,
        scope='ONLY LittleX and IssueDesk. Independent fresh workflow trials, not correctness samples or steady-read replicates')
    write(output/'index.json', index)
    try:
        with SmallPostgres(args.cluster, Path(read_json(release.runtime_manifest)['root']),statement_logging=False) as pg:
            pg.release = release; pg.metrics_directory = metric_dir
            gate.require(pg.sql('SHOW log_statement')=='none','Primary server SQL logging must be OFF')
            index['server_log_statement']='none'
            for row in schedule():
                gate.require(shutil.disk_usage(output).free >= 3*1024**3, 'Capacity guard: less than3GiB')
                app = row['app']; directory = output/row['trial_id']
                if app in suite.native.SOURCES:
                    types = sum((list(x) for x in suite.native.TYPES[app]), [])
                else:
                    text = '\n'.join(p.read_text() for p in (OLD_SUITE.parent/'app_suite/apps'/app).glob('*.jac'))
                    types = re.findall(r'\b(?:node|edge)\s+(\w+)\s*\{', text)
                pg.cleanup_context = dict(app=app,config_id=row['config_id'],seed=42,mode='live_cleanup',
                    run_directory=str(output),case_directory=str(directory),
                    acceptance_directory=str(output/'cleanup-acceptance'),sources=closure,
                    cleanup_review=cleanup_review,source_manifests=cleanup_manifests,
                    cas_references=[],cas_roots=[],domain_types=types,expected=baselines[app])
                result = suite.run(app,row['config_id'],directory,pg,release.runtime_manifest,release.overlay_manifest,
                    expected=baselines[app],stage='formal',seed=42,
                    release=release)
                seal = verify_case(directory, required=('continuation-proof.json',))
                metric_path = metric_dir/(directory.name+'.json')
                gate.require(read_json(metric_path)['raw_seal'] == seal, 'Metrics/raw accepted seal mismatch')
                index['cases'].append(dict(**row,passed=True,raw_seal=seal,
                    metrics=dict(path=str(metric_path),sha256=sha256(metric_path)),proof=result['proof']))
                write(output/'index.json', index)
                print(json.dumps(dict(completed=len(index['cases']),total=48,**row)),flush=True)
        gate.revalidate(release)
        index.update(status='complete',passed=len(index['cases'])==48)
    except BaseException as error:
        index.update(status='failed_or_interrupted',passed=False,error=f'{type(error).__name__}: {error}')
        raise
    finally:
        index['completed_utc']=datetime.now(timezone.utc).isoformat()
        write(output/'index.json', index)


if __name__ == '__main__':
    main()
