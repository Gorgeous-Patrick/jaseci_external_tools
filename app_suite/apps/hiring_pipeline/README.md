# HiringPipeline

Create candidates, apply to jobs, schedule two required rounds, score interviews and issue capacity-limited offers.

The domain is stored in native Jac nodes and typed edges in `server.jac`. Each
authenticated evaluation operator owns an independent graph. Named customers,
reviewers, candidates and similar records are domain entities, not separate auth
accounts unless explicitly modeled. Shared auth and UI primitives are provided
by the suite; this application has its own domain walkers and interaction flow.

## Deterministic workflow and oracle

Run with seed 42. Seed is idempotent, and all demo records/messages are English.
The native scenario is `additional_scenarios.py:hiring_pipeline`; its expected values and
negative paths are independent assertions, not generated from native reports.

One scorecard per round, required threshold, job capacity and candidate offer exclusivity.

The browser scenario in `additional_browser.mjs` enters real forms, invokes
native walkers and checks rendered business state. After another backend process
restart, `additional_scenarios.verify_browser` inspects the persisted result.

## Evaluate and launch

From the external-tools repository, using suite README prerequisites:

```sh
python3 app_suite/evaluate.py --apps hiring_pipeline --seed 42 --browser --policy none --runtime-source /tmp/ttg-app-suite-runtime-frozen-20261029 --output /tmp/hiring_pipeline-none42
python3 app_suite/evaluate.py --apps hiring_pipeline --seed 42 --browser --policy ttg --runtime-source /tmp/ttg-app-suite-runtime-frozen-20261029 --output /tmp/hiring_pipeline-ttg42
TTG_RUNTIME_SOURCE=/tmp/ttg-app-suite-runtime-frozen-20261029 python3 app_suite/launch.py --state /tmp/hiring_pipeline-none42 --app hiring_pipeline
```

Open the printed loopback URL. Username: `user_0000`; password:
`isolated-suite-seed-password`. Ctrl-C stops only the launcher's owned services.
The persisted graph remains in the selected state directory. Evidence directories
must be new; functional acceptance includes native, browser, ownership and restart
gates. Source-freshness and both-policy acceptance are checked by `status.py`.

These are synthetic sequential business workflows. Concurrent contention and
external production integrations are outside the verified scope. Performance
measurements are separate and remain unmeasured in functional summaries.
