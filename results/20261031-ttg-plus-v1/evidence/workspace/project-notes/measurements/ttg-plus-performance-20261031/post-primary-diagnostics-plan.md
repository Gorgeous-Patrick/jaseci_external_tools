# Conditional diagnostics after the complete36-trial primary study

This is a plan only. It lives outside the frozen execution/numeric closure. No
diagnostic service, query, profile or capture change starts until all36 primary
trials finish, owned primary services stop, and the numerical export is accepted.
The primary runtime, observer, raw data and results remain version-bound.

Start with the accepted per-request SQL traces and compact outcome references.
For every regressing cell, compare the three measured workflows and identify
actual SQL fingerprints, data/control counts, rows, returned bytes, role/backend
intervals and protocol contributions. Report observed variation and preserve
all9 cells. Choose a bounded diagnostic subset only where those observations
leave a concrete question: initially at most two app/config/request combinations,
with their selection reason bound to the accepted export. Query-count changes
and larger individual protocol intervals can explain the measured composition
without asserting CPU, server-planning or network causes.

For selected slow data statements, use a separately owned diagnostic database
with the same source, schema, indexes, seeded data, action position and access
context. Bind the exact typed SQL and parameter values, actor/origin identities,
transaction state, relevant session settings and pre-statement state. Restore
physical IDs and topology where replaying a recorded instance. Check an existing
preserved v4 database's owner, runtime, seed, mapping, census and action position
before considering it; v4 LL1000 is a read-only workflow, whereas a LittleX
mutation requires the correct pre-statement state. Use a fresh equivalent clone
when state or transaction visibility cannot be established. Keep provisioning,
state checks and setup outside diagnostic query intervals.

The primary sink retains original/positional SQL, framing counts, fingerprints
and byte totals; it does not persist Bind parameter bytes. This is verified in
the unchanged continuation_probe.flush/_packet implementation. Therefore exact
primary parameter replay is claimed only when every binding can be recovered
unambiguously from sealed inputs/contracts and verified against the frozen SQL
compiler. Otherwise perform a clearly labelled matched diagnostic workflow
recapture: same sealed fixture/actions, correctness and query-count/fingerprint
checks, with exact encoded Bind values and a pre-statement state snapshot saved
by a disclosed diagnostic-only boundary overlay. Those SQL/parameters are exact
for the diagnostic instance; a fresh physical UUID mapping is documented rather
than represented as literal primary-instance replay. No parameter is guessed.

Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) on the selected actual SQL and exact
diagnostic bindings. Retain planning/execution times, complete plan, estimated
and actual rows/loops, buffer hits/reads/temp activity, server settings/version,
SQL/bind hashes and database-state hashes. Capture a first and repeated execution
with their cache state explicit. Separate EXPLAIN's server-reported times from
primary send-to-ReadyForQuery wall intervals. Controls such as DISCARD ALL or
COMMIT are attributed by their measured command counts/protocol contributions;
they are not treated as explainable SELECTs. A selected mutating statement uses
a restored pre-statement clone and a rollback/discarded clone after measurement;
rollback alone is insufficient for sequence or external effects.

CPU/path-planning conclusions require a separate diagnostic capture. First
validate any custom thread-CPU/cProfile timer with controlled busy and blocking
work, one identified foreground OS thread, independent thread_time_ns totals,
and checks for impossible/negative entries or cross-thread contamination. A
failed timer validation excludes CPU comparisons. A default cProfile run is
labelled call/wall including I/O. Preserve walker callback identity: instrument
dispatcher/rt.invoke or disclosed source boundaries, never replace ability class
methods. Verify native outputs, plan/submission counts and SQL execution/counts
against the unprofiled counterpart. Name each thread-CPU scope precisely; a
planner call may include resolver/client-driver CPU, and it does not measure
server CPU. Child-process/IPC CPU requires separately identified process/thread
evidence. Keep all diagnostic timings apart from the primary dataset.

Seal diagnostic source/patch, selection, SQL/bind/state inputs, raw plans,
profiles, timer validation and outcomes under a new diagnostic manifest. Use one
owned DB at a time, preserve failures and existing ownership/session cleanup
guards. No blanket profiling or result-driven tuning of the completed primary
experiment is part of this plan.
