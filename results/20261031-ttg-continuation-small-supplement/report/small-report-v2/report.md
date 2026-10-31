# TTG continuation: partial two-application study

Scope: LittleX and IssueDesk only, six configurations, runtime866222, seed42, workers1/limit256.
Twelve excluded warmup workflows and36 measured fresh workflows; n3 per application/policy.
Primary: actual PgWire send-to-ReadyForQuery protocol completion wall. Summed calls and interval union are separate.
Includes foreground/background and transaction control SQL attributed to business requests. Setup, auth, seed, steady warmup and verification are retained separately.
Each measured workflow starts a fresh database and profile. Learning is natural within that workflow; warmup/profile state never carries across trials.

## LittleX

| Policy | DB sum ms [IQR] | DB union ms [IQR] | SQL total/data/control/other | FG/BG distinct-backend overlap ms |
|---|---:|---:|---:|---:|
| Off | 39.859 [1.236] | 39.859 [1.236] | 153/90/63/0 | 0.000 |
| Legacy TTG / thread | 116.583 [1.556] | 116.400 [1.532] | 144/74/70/0 | 0.141 |
| Always / thread | 50.362 [8.214] | 43.831 [7.562] | 167/90/77/0 | 0.000 |
| Always / process | 49.514 [2.891] | 49.514 [2.891] | 159/90/69/0 | 0.000 |
| Expected benefit / thread | 47.846 [2.153] | 42.873 [1.440] | 165/90/75/0 | 0.000 |
| Expected benefit / process | 50.053 [1.206] | 50.053 [1.206] | 159/90/69/0 | 0.000 |

## IssueDesk

| Policy | DB sum ms [IQR] | DB union ms [IQR] | SQL total/data/control/other | FG/BG distinct-backend overlap ms |
|---|---:|---:|---:|---:|
| Off | 140.773 [11.417] | 140.773 [11.417] | 555/366/189/0 | 0.000 |
| Legacy TTG / thread | 296.063 [16.585] | 293.819 [16.541] | 569/354/215/0 | 3.043 |
| Always / thread | 142.029 [2.018] | 142.029 [2.018] | 563/366/197/0 | 0.000 |
| Always / process | 188.234 [24.292] | 188.234 [24.292] | 559/366/193/0 | 0.000 |
| Expected benefit / thread | 145.973 [5.113] | 145.973 [5.113] | 561/366/195/0 | 0.000 |
| Expected benefit / process | 148.872 [0.697] | 148.872 [0.697] | 558/366/192/0 | 0.000 |

## Evidence

All raw samples/query traces, actual backend/child PID pairs, model outcomes and phase exclusions are referenced by results.json.
The trace supplement accounts for protocol interval overlaps by foreground/background roles and actual backend/client identities.
Read-only SQL fingerprint contributions and native model scope/checkpoint snapshots are bound in figure-inputs.json.
Numeric export SHA256: 17922e61bcf4ff4ca6814a1b23cd758d0ac371d979f1537ab95dc802233c2f4b
Main authorization SHA256: d1fc7443300f79ce5bc2185f900182466d60bed336906d99c54540c585d1dc02
