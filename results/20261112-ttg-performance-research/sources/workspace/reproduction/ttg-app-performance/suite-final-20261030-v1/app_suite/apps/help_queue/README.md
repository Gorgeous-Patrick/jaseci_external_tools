# HelpQueue

HelpQueue manages customer support tickets, agent assignments, response SLAs,
replies and resolution. A deterministic simulation clock makes deadlines
reproducible. Urgent tickets require a first response before 30 minutes; normal
tickets allow 120. At the deadline, an unanswered open ticket escalates to senior
agent Sam. A late first reply also records escalation even without an earlier
explicit SLA evaluation. Resolved tickets retain their reply and escalation history.

Native nodes: SupportDesk, Customer, Agent, SLA, Ticket and Reply. Typed edges
connect tickets to their opening customer, assigned agent, SLA and replies.
EvaluateSLA transports the desk clock from one native ability to ticket abilities
that decide the deadline branch and update agent relationships.

Seed 42 creates Research Help Desk at minute 1000, North/South Lab customers,
Riley (tier 1), Sam (tier 2), both SLA policies and Sensor offline. Seeds 43/44
start at minutes 1001/1002. Each authenticated operator owns an independent desk;
customer and agent records are domain entities rather than separate auth accounts.

```sh
python3 app_suite/evaluate.py --apps help_queue --seed 42 --browser --runtime-source /tmp/ttg-app-suite-runtime-frozen-20261029 --output /tmp/help-queue-seed42
python3 app_suite/launch.py --state /tmp/help-queue-seed42 --app help_queue --port 18708
```

Run from external-tools with suite prerequisites. Sign in as `user_0000` using
`isolated-suite-seed-password`. Open a ticket, assign an agent, advance the
simulation clock and evaluate SLAs. Reply and resolve; unresolved tickets cannot
be closed without a reply, and escalated tickets cannot be downgraded to tier 1.

The native oracle tests the exact deadline boundary, urgent/normal routing,
assignment replacement, late replies, resolution rules, invalid clock changes
and cross-user isolation. It independently checks first-response age against the
SLA. Browser validation opens an urgent ticket, observes rejected early resolution,
triggers escalation, replies and resolves. Native state is inspected after restart.
