# CoursePath

CoursePath manages course modules, lesson prerequisites, learner enrollment and
durable progress. Course, Module and Lesson nodes are shared by independent
Enrollment graphs. Completion records link each enrollment to a specific lesson,
so one learner's progress never unlocks another learner's lesson.

Graph: `Course -> HasModule -> Module -> HasLesson -> Lesson`,
`dependent Lesson -> Requires -> prerequisite Lesson`, and
`Enrollment -> EnrolledIn -> Course`,
`Enrollment -> HasCompletion -> Completion -> ForLesson -> Lesson`.

Seed 42 creates Graph Systems with Foundations and Applied Traversal modules.
The lesson chain is Nodes, Edges, Traversal, Optimization. Nodes takes 10 minutes
at seed 42, 11 at seed 43 and 12 at seed 44. Enroll a learner, complete each
prerequisite in order and inspect progress. Add lessons to modules with an
optional existing prerequisite. A new lesson updates every enrollment's total.
Repeated enrollment/completion is idempotent and preserves one completion record.

```sh
python3 app_suite/evaluate.py --apps course_path --seed 42 --browser --output /tmp/course-path-seed42
python3 app_suite/launch.py --state /tmp/course-path-seed42 --app course_path --port 18705
```

Run from external-tools; suite README lists prerequisites. Sign in as `user_0000`
with `isolated-suite-seed-password`. The native oracle checks exact seed shape,
learner separation, ordered prerequisites, duplicate completion suppression,
dynamic lesson totals, completion sequences and cross-user isolation. Browser
validation enrolls a learner, attempts a locked lesson and completes all lessons
in order. Exact native state and browser progress must survive process restarts.
