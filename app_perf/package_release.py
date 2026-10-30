#!/usr/bin/env python3
"""Package the completed local study without changing its frozen evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", default="reports-v3")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    evidence = workspace / "project-notes/measurements/ttg-app-performance-20261030"
    formal = evidence / "formal-v1"
    trials = json.loads((formal / "trials.json").read_text())
    assert trials["status"] == "complete" and len(trials["rows"]) == 480
    assert sum(row["measured"] for row in trials["rows"]) == 360
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    inventory = {}

    def archive(name, paths):
        target = output / "raw" / (name + ".tar.gz")
        with target.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as tar:
                    for path in sorted(set(paths)):
                        relative = str(path.relative_to(workspace))
                        digest = sha(path)
                        info = tar.gettarinfo(str(path), arcname=relative)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        with path.open("rb") as file:
                            tar.addfile(info, file)
                        assert sha(path) == digest, relative
                        inventory[relative] = digest
        assert target.stat().st_size < 95_000_000, "Split archive before publishing"

    def sealed_case(directory):
        manifest = directory / "artifacts.json"
        seal = json.loads(manifest.read_text())
        paths = [manifest]
        for name, expected in seal["files"].items():
            path = directory / name
            assert sha(path) == expected, path
            paths.append(path)
        return paths

    for app in dict.fromkeys(row["app"] for row in trials["rows"]):
        paths = []
        for row in trials["rows"]:
            if row["app"] == app:
                paths.extend(sealed_case(Path(row["directory"])))
        archive(app, paths)

    diagnostic = evidence / "diagnostics-v2"
    paths = []
    for summary in diagnostic.glob("*/summary.json"):
        paths.extend(sealed_case(summary.parent))
        paths.extend((summary.parent / "foreground-profiles").glob("*"))
    paths.extend((diagnostic / "postgres/data/logs").glob("*.csv"))
    paths.extend(path for path in diagnostic.glob("*.json") if path.is_file())
    archive("separate-diagnostics", paths)

    paths = []
    for directory in [evidence / "review-ready-v2", evidence / "final-acceptance-v1",
                      workspace / "project-notes/measurements/ttg-app-main-review-20261030"]:
        paths.extend(path for path in directory.rglob("*") if path.is_file())
    paths.extend(path for path in evidence.glob("*.json") if path.is_file())
    paths.extend((evidence / "protocol-validation-v8-quiet").glob("*.json"))
    paths.append(evidence / "preflight-v6/preflight.json")
    paths.extend([evidence / "preflight-v6/littlex-dependency_always/server.jac",
                  evidence / "preflight-v6/jacord-dependency_always/server.impl.jac"])
    source = workspace / "reproduction/ttg-app-performance"
    for name in ["runtime-5f94eb62d-v2", "runtime-primary-boundary-5f94eb62d-v1",
                 "suite-final-20261030-v1"]:
        paths.append(source / name / "snapshot.json")
    paths.extend(path for path in (source / "suite-final-20261030-v1").rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts)
    archive("provenance", paths)

    for path in formal.glob("*.json"):
        shutil.copy2(path, output / path.name)
    shutil.copy2(formal / "per-app-results.csv", output / "per-app-results.csv")
    shutil.copytree(evidence / args.report, output / "report")
    source_hashes = {}
    destination = Path(__file__).resolve().parent
    for path in source.iterdir():
        if path.is_file() and path.suffix in (".py", ".sh", ".md"):
            shutil.copy2(path, destination / path.name)
            source_hashes[path.name] = sha(path)
    (output / "README.md").write_text("""# TTG application performance — October 30, 2026

The study covers 30 entries: LinkedList and 29 full applications, including LittleX,
Jacord and JDrive. All 480 cases passed: 120 excluded warmups and 360 measured
fresh-database trials, with three independent trials per application and policy.

- `report/ttg-app-performance.pdf`: English presentation.
- `report/REPORT.md`: tables, methods and per-application observations.
- `per-app-results.csv` and `results.json`: measured DB protocol times and SQL counts.
- `raw/<app>.tar.gz`: every sealed artifact from that application's 16 cases,
  including excluded warmups, actual SQL traces, fixtures, actions and oracles.
- `raw/separate-diagnostics.tar.gz`: 20 separate diagnostic cases, independent
  PostgreSQL CSV records and preserved CPU captures.
- `raw/provenance.tar.gz`: frozen suite sources, review/release manifests,
  runtime file inventories, acceptance metadata and independent main-agent audits.
- `release.json`: archived member hashes, archive hashes and measurement-source hashes.

The primary metric is send-to-ReadyForQuery protocol completion wall time, including
database work, transport and driver decoding. The report separates summed intervals,
interval unions and driver-call times. It reports actual SQL dispatches and controls.

Original TTG lowered the full-workflow median for LinkedList. All 29 full applications
had higher medians in this local seed42 study. The dependency configurations issued
the same SQL counts as prefetch off; recorded checkpoints considered zero plans.
The report traces concrete admission barriers and added recursive SQL costs.

All CPU comparisons were excluded after impossible negative profile times were found.
The original diagnostic log selector failed; a separately tested reconciliation adapter
validated all 20 cases against actual `jac:<PID>:run` PostgreSQL backend labels.
The report and raw evidence retain both findings.

Archives store paths relative to the original workspace root. Extract them there to
restore the historical evidence tree. Absolute paths in historical manifests identify
the capture location. App implementations live in `../../app_suite`; the measurement
sources are copied unchanged to `../../app_perf`. Their historical README describes
the original workspace layout. A new measurement requires a fresh freeze and release
review rather than reusing the historical authorization. PostgreSQL physical data
directories and compiler caches are retained locally and excluded from this package.
""")
    release = {"status": "complete", "cases": 480, "measured_cases": 360,
               "apps": 30, "policies": 4, "independent_trials_per_cell": 3,
               "runtime_commit": "5f94eb62da2857ab991de704935e7333b405cb8e",
               "source_copy_sha256": source_hashes, "archived_file_sha256": inventory,
               "files": {str(path.relative_to(output)): sha(path)
                         for path in output.rglob("*") if path.is_file()},
               "archive_root": "Extract archives into the original workspace root; stored absolute paths identify the historical capture location.",
               "cpu_profiles": "Unaccepted: custom timer produced negative times. Raw data retained; all CPU conclusions excluded."}
    (output / "release.json").write_text(json.dumps(release, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
