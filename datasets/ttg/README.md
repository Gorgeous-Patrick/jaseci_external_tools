# TTG application dataset

A reproducible synthetic graph corpus for LinkedList, LittleX, Jacord and JDrive.
Each dataset contains initial graph state, an ordered read/write session and
logical expected results. Native application import and replay are the next
integration stage; their status is explicit in each manifest.

## Application coverage

| Application | Graph | Session | TTG question |
| --- | --- | --- | --- |
| LinkedList | Item → Next → Item | Traverse, Sum, Find at head/middle/tail, failed Find | How much does early termination waste? |
| LittleX | Profile → Follow → Profile; Profile → Post → Tweet | Feed, filtered feed, like/unlike, new follow, refreshed feed, post, refreshed feed | How do shared targets, result filtering and writes affect reuse? |
| Jacord | Workspace → HasChannel → Channel; Message → Posted → Channel; reply → ReplyTo → parent; Message → AuthoredBy → User | Open two channels, reply, reopen first channel | How do variable reply depth and shared authors affect prefetch? |
| JDrive | Drive → Contains → Folder → Folder/File | List, recursive visible tree, trash subtree, revisit, create folder, revisit | How much data lies behind a pruned branch? |

LittleX search filters results after traversal in the current source. A smaller
search result therefore does not imply fewer accessed nodes. JDrive prunes
trashed children before visiting them. Jacord traverses **incoming** Posted and
ReplyTo edges. These differences are preserved in the reference interpreter.
LinkedList Traverse stops at 10,000 items; Find stops on the first match.

## Generate and verify

From the external-tools checkout:

```sh
python3 datasets/ttg/build.py build --scale small --seed 42 --output /tmp/ttg-small-42
python3 datasets/ttg/build.py validate /tmp/ttg-small-42
python3 -m unittest discover -s datasets/ttg -p test_build.py -v
```

The source root defaults to the parent directory containing the external-tools,
Jacord and JDrive checkouts. Override it with `--source-root` when needed.
Output application directories must be new. Generation leaves existing datasets
intact. The smoke corpus is included under `data/smoke`; larger data belongs in
an experiment directory, generated using the same script.

| Scale | List length | LittleX users × posts | Jacord channels × top-level messages | JDrive depth / fanout |
| --- | ---: | ---: | ---: | ---: |
| smoke | 32 | 6 × 4 | 2 × 8 | 3 / 3 |
| small | 1,000 | 50 × 20 | 5 × 100 | 5 / 3 |
| medium | 10,000 | 500 × 100 | 10 × 1,000 | 7 / 3 |

Jacord adds nested replies drawn from `[0, 0, 0, 1, 2, 5]` for each top-level
message. User count follows the scale's LittleX user count. JDrive includes a
populated hidden top-level branch, then independently marks 20% of deeper
folders as trashed. Each non-leaf folder has a small file sibling. LittleX
combines a hot account, a ring neighbor and a random follow target. These are
specified synthetic distributions; future production traces can supply measured
parameters. LinkedList is deterministic across seeds.

Use seeds 42 / 43 / 44 for development / validation / evaluation. Each split is
an independently generated initial graph and session; mutations are replayed
in order within a session. Node IDs are logical identifiers local to a dataset.

## Files and contracts

- `nodes.jsonl`: `{id, type, fields}`, one node per line.
- `edges.jsonl`: `{source, type, target}`, in stable insertion order.
- `operations.jsonl`: ordered logical operations, including mutations.
- `expected.jsonl`: normalized logical result for each operation after all prior mutations.
- `manifest.json`: seed, dimensions, source commits and source-file SHA256 values,
  dirty-checkout status, per-type counts, artifact hashes and native integration status.

Expected collections use sorted unique logical IDs, except Traverse, which
preserves path order. Scalar results retain their value. This checks logical
membership; native adapters should additionally validate native report fields,
ordering and multiplicity against their application's API contract. Result IDs
are separate from the nodes read to produce those results. The runtime access
trace supplies actual demand/prefetch usefulness labels.

The importer contract is to create actual application node and edge types,
record logical-to-runtime IDs, preserve edge directions and insertion order,
create authenticated user roots and grants matching the app, and store file
bytes through JDrive's storage interface. A dataset's File `blob_key` is a
logical key; the importer maps it to real storage. This corpus records the
file's declared 64-byte size; integration should supply 64 bytes deterministically.

An operation adapter maps logical actions to native walkers. LittleX profile
ownership and Jacord authorship must come from the authenticated user, as in the
original apps. After importing, compare counts, fields and topology before
snapshotting. After replay, compare normalized results at every step and check
mutations through subsequent reads. A native replay is marked passed only after
these checks run on a real Jac backend.

## Measurement protocol

`experiment.json` specifies the paired policy/RTT/cache matrix. Run each policy
from the same starting snapshot; keep caches alive throughout the session.
Compare disabled, existing TTG and dependency-based TTG. All three must pass the
same semantic checks before performance is accepted.

Record driver-boundary DB-call wall time and actual SQL count for both demand
and background workers. Separate connection/transaction setup, discovery,
payload, cleanup and fallback commands. Concurrent DB-call durations can overlap;
retain timestamps and report foreground critical-path wait separately. Log HTTP
or walker time as an additional metric with its own boundary. RTT settings need
measured calibration using a simple query.

For overfetch, record prefetched node versions and bytes, later consumption,
invalidation and duplicate fetches. Report useful/unused bytes, cache hits,
late prefetch and demand fallback. Complete background attribution after the
foreground session ends. Primary timing runs and detailed cProfile runs are
separate executions with matching workload manifests.

## Next applications and additional dependency cases

| Candidate | Workload | Added coverage |
| --- | --- | --- |
| Fraud detection (existing `fraud_detect/`) | Account → Transaction → Account, threshold tests, early stop | Alternating node types, accumulated walker state and cyclic reachability |
| Issue tracker | Project → Issue → Comment/User, permission and status predicates | Shared users, authorization branches and frequent updates |
| Approval workflow | Request → ApprovalStep → Approver, computed routing | A decision computed in one ability determines a later ability's trace |

Start with the existing fraud-detection source, then add the approval workflow
if the four applications do not exercise a dependency pattern. Include controlled
FIFO cases where intervening nodes modify either irrelevant state or a branch
input, and a cancellation case. Pair these with native execution traces to test
prediction stability and invalidation. New app selection follows these coverage
needs; the four existing applications remain the first integration target.
