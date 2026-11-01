# TTG+: fused traversal SQL

Three workloads × three configurations × three measured fresh workflows, with nine excluded warmups.
Primary: actual PgWire send-to-ReadyForQuery protocol completion wall; sum and interval union reported separately.
SQL counts include all real foreground/background data, path and transaction-control dispatches.
Runtime 85026d486de8e16d4b894aa5a5664c7873893e89; seed42; process workers1; prefetch_limit2048; common abstract-step budget32768.

## LinkedList · 32 nodes

| Configuration | DB sum ms | DB union ms | SQL total/data/control/other |
|---|---:|---:|---:|
| Off | 114.325 [114.149–122.103] | 114.325 [114.149–122.103] | 360/318/42/0 |
| Repaired pre-fusion / process | 121.755 [121.182–136.588] | 121.755 [121.182–136.588] | 365/318/47/0 |
| TTG+ / process | 94.459 [94.404–101.485] | 94.459 [94.404–101.485] | 243/196/47/0 |

## LinkedList · 1,000 nodes

| Configuration | DB sum ms | DB union ms | SQL total/data/control/other |
|---|---:|---:|---:|
| Off | 3310.437 [3130.876–3312.781] | 3310.437 [3130.876–3312.781] | 9072/9030/42/0 |
| Repaired pre-fusion / process | 3481.763 [3448.737–3500.474] | 3481.763 [3448.737–3500.474] | 9077/9030/47/0 |
| TTG+ / process | 2336.291 [2300.719–2359.249] | 2336.291 [2300.719–2359.249] | 5083/5036/47/0 |

## LittleX · original workflow

| Configuration | DB sum ms | DB union ms | SQL total/data/control/other |
|---|---:|---:|---:|
| Off | 41.426 [37.734–41.728] | 41.426 [37.734–41.728] | 153/90/63/0 |
| Repaired pre-fusion / process | 49.324 [47.245–51.183] | 49.324 [47.245–51.183] | 159/90/69/0 |
| TTG+ / process | 55.435 [55.168–59.843] | 55.435 [55.168–59.843] | 147/78/69/0 |

## Traverse SQL decomposition

| Size | Mode | Ordinary path | Fused path | Payload | Control | Identity + catalog | Total |
|---|---|---:|---:|---:|---:|---:|---:|
| LL 32 | Off | 32 | 0 | 35 | 7 | 2 | 76 |
| LL 32 | Repaired pre-fusion / process | 32 | 0 | 35 | 8 | 2 | 77 |
| LL 32 | TTG+ / process | 0 | 1 | 5 | 8 | 2 | 16 |
| LL 1000 | Off | 1000 | 0 | 1003 | 7 | 2 | 2012 |
| LL 1000 | Repaired pre-fusion / process | 1000 | 0 | 1003 | 8 | 2 | 2013 |
| LL 1000 | TTG+ / process | 0 | 1 | 5 | 8 | 2 | 16 |

## Branch-sensitive eligibility

The actual middle, tail and missing Find outcomes record `Unknown scalar fact: 'visit_item::here.value'`. Their fused-query counts are 500, 999 and 1,000. Each query caches one origin, retaining per-step path dispatch counts.

| Operation (1,000 nodes) | Off SQL | Pre-fusion SQL | TTG+ SQL |
|---|---:|---:|---:|
| Traverse | 2012 | 2013 | 16 |
| Sum | 2012 | 2013 | 16 |
| Find head | 12 | 12 | 12 |
| Find middle | 1013 | 1014 | 1014 |
| Find tail | 2011 | 2012 | 2012 |
| Find missing | 2012 | 2013 | 2013 |

## LittleX trace attribution

All nine measured workflows return 108 payload rows and 70,163 protocol row-payload bytes for fingerprint b0075df9. Off and pre-fusion issue 52 payload calls; TTG+ issues 44. These row counts do not identify distinct application IDs.
The batched 3166e116 query contributes 9.680058 ms mean summed protocol time across four calls per workflow. Recursive d1067307 contributes 7.932784 ms across six calls. These are protocol contributions, not server-only or CPU timings.

## Matched server-plan diagnostic

One off and one TTG+ full native workflow passed the same business/state/restart oracles. Five selected original SQL calls completed; ten EXPLAIN plans use their exact diagnostic Bind bytes in the same recorded SERIALIZABLE transaction. Census and repeated EXPLAIN warm the buffers. This diagnostic is separate from primary n3 protocol timing.

| Region | Observation | SQL | Planning ms | Execution ms | Rows | Root shared hits |
|---|---|---|---:|---:|---:|---:|
| Root → Profile | First | Native | 0.315 | 0.092 | 1 | 12 |
| Root → Profile | First | Fused | 0.742 | 0.184 | 1 | 22 |
| Collect: Post + Follow | First | Native | 0.943 | 0.278 | 12 | 55 |
| Collect: Post + Follow | First | Fused | 1.203 | 0.535 | 12 | 320 |
| Root → Profile | Repeat | Native | 0.244 | 0.070 | 1 | 9 |
| Root → Profile | Repeat | Fused | 0.617 | 0.094 | 1 | 22 |
| Collect: Post + Follow | Repeat | Native | 0.964 | 0.180 | 12 | 55 |
| Collect: Post + Follow | Repeat | Fused | 1.181 | 0.423 | 12 | 320 |

## Next experiments

Test an indexable target-ID join in the fused SQL AST while preserving ACL, exact type/module, cardinality and ordered cache semantics. Test admission that accounts for proven multi-origin savings and retains per-path execution for uneconomic single-origin regions. Test prepared-plan reuse with complete native correctness. These are proposed experiments; no improvement result is claimed.

