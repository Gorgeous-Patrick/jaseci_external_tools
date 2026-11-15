# LabSamples

Split samples into aliquots, assign batches, record QC failures and retests, then release passing batches.

The domain is stored in native Jac nodes and typed edges in `server.jac`. Each
authenticated evaluation operator owns an independent graph. Named customers,
reviewers, candidates and similar records are domain entities, not separate auth
accounts unless explicitly modeled. Shared auth and UI primitives are provided
by the suite; this application has its own domain walkers and interaction flow.

## Deterministic workflow and oracle

Run with seed 42. Seed is idempotent, and all demo records/messages are English.
The native scenario is `additional_scenarios.py:lab_samples`; its expected values and
negative paths are independent assertions, not generated from native reports.

Initial volume = remaining + aliquots; latest QC must pass and released results are immutable.

The browser scenario in `additional_browser.mjs` enters real forms, invokes
native walkers and checks rendered business state. After another backend process
restart, `additional_scenarios.verify_browser` inspects the persisted result.

## Evaluate and launch

From the external-tools repository, using suite README prerequisites:

```sh
python3 app_suite/evaluate.py --apps lab_samples --seed 42 --browser --policy none --runtime-source /tmp/ttg-app-suite-runtime-frozen-20261029 --output /tmp/lab_samples-none42
python3 app_suite/evaluate.py --apps lab_samples --seed 42 --browser --policy ttg --runtime-source /tmp/ttg-app-suite-runtime-frozen-20261029 --output /tmp/lab_samples-ttg42
TTG_RUNTIME_SOURCE=/tmp/ttg-app-suite-runtime-frozen-20261029 python3 app_suite/launch.py --state /tmp/lab_samples-none42 --app lab_samples
```

Open the printed loopback URL. Username: `user_0000`; password:
`isolated-suite-seed-password`. Ctrl-C stops only the launcher's owned services.
The persisted graph remains in the selected state directory. Evidence directories
must be new; functional acceptance includes native, browser, ownership and restart
gates. Source-freshness and both-policy acceptance are checked by `status.py`.

These are synthetic sequential business workflows. Concurrent contention and
external production integrations are outside the verified scope. Performance
measurements are separate and remain unmeasured in functional summaries.
