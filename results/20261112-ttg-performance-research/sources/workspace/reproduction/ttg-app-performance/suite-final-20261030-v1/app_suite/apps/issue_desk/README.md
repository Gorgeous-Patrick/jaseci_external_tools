# IssueDesk

IssueDesk manages project issues with engineer assignments, ordered comments and
blocking dependencies. Native Jac nodes store the entire domain; the frontend
performs mutations through native walkers and refreshes the project board.

## Domain and workflow

`Project -> HasIssue -> Issue`, `Project -> HasEngineer -> Engineer`,
`Issue -> AssignedTo -> Engineer`, `Issue -> HasComment -> Comment`, and
`blocking Issue -> Blocks -> dependent Issue` form the persistent graph.
Multiple issues share engineers. ProjectBoard traverses issues and engineers;
issue views read incoming blocking edges, assignees and comments. ReachIssue
uses a visited set and native visit statements to reject dependency cycles.

Seed 42 creates the TTG Runtime project, Avery and Morgan, a parser issue blocking
a runtime release, and one ordered comment. Seeds 43 and 44 change the parser's
priority deterministically. Seed is idempotent within a user's root.

Create an issue, assign Morgan, add a comment, and select an existing blocker.
Closing is rejected while any blocker remains open. Close blockers first, then
close the issue. Reopening a blocking issue is rejected while a closed dependent
would become inconsistent. A separate authenticated user cannot read or mutate
the owner's project.

## Validate

From the external-tools repository:

```sh
python3 app_suite/evaluate.py --apps issue_desk --seed 42 --browser --output /tmp/issue-desk-seed42
```

Resume the persisted application for interactive use with:

```sh
python3 app_suite/launch.py --state /tmp/issue-desk-seed42 --app issue_desk --port 18701
```

Open the printed URL and sign in as `user_0000`, password
`isolated-suite-seed-password`. The launcher uses the existing suite database and
source snapshot, chooses independent backend/PostgreSQL ports, and stops its own
processes on Ctrl-C. Domain changes survive subsequent launches.

See the suite README for runtime and browser prerequisites. The command owns its
isolated PostgreSQL cluster and loopback servers. Evidence includes every native
walker input and result, domain assertions, expected final state, exact state
equality after restart, a browser trace and screenshot, and native checks of
browser-created state after another restart. `--policy ttg` selects existing TTG;
it does not enable the separate experimental dependency-analysis prototype.

The native oracle checks seeded membership, priority, assignment cardinality,
ordered comment bodies, dependency direction/idempotence, cycle/self-blocking
rejection, close/reopen transitions and cross-user isolation. Browser validation
uses actual form inputs and clicks for creation, assignment, comments, dependency
selection, rejected closure and successful closure after resolving the blocker.
HTTP timings are diagnostic; DB-call time and SQL count remain null until measured.
