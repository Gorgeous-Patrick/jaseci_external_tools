"""CoursePath: enrollments, shared lesson prerequisites and durable learner progress."""

import from typing { cast }

node Course {
    has title: str;
}
node Module {
    has title: str,
        position: int;
}
node Lesson {
    has title: str,
        position: int,
        minutes: int;
}
node Enrollment {
    has learner: str;
}
node Completion {
    has sequence: int;
}
edge HasModule {}
edge HasLesson {}
edge Requires {}
edge EnrolledIn {}
edge HasCompletion {}
edge ForLesson {}

def _owned_course(course: object) -> bool {
    return isinstance(course, Course)
        and jid(course) in [jid(item) for item in [root-->[?:Course]]];
}

def _course_lessons(course: Course) -> list[Lesson] {
    lessons: list[Lesson] = [];
    for module in [course->:HasModule:->[?:Module]] {
        lessons.extend([module->:HasLesson:->[?:Lesson]]);
    }
    return lessons;
}

def _enrollment_view(enrollment: Enrollment) -> dict {
    course = [enrollment->:EnrolledIn:->[?:Course]][0];
    completed = [];
    for completion in [enrollment->:HasCompletion:->[?:Completion]] {
        lesson = [completion->:ForLesson:->[?:Lesson]][0];
        completed.append({"lesson_id": jid(lesson), "sequence": completion.sequence});
    }
    return {
        "id": jid(enrollment),
        "learner": enrollment.learner,
        "course_id": jid(course),
        "completed": completed,
        "total_lessons": len(_course_lessons(course))
    };
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Course]] {
            report {"ok": True, "created": False};
            return;
        }
        course = here ++> Course(title="Graph Systems");
        foundations = course +>:HasModule:+> Module(title="Foundations", position=1);
        applied = course +>:HasModule:+> Module(title="Applied Traversal", position=2);
        nodes = foundations +>:HasLesson:+> Lesson(
            title="Nodes", position=1, minutes=10 + self.seed % 3
        );
        edges = foundations +>:HasLesson:+> Lesson(
            title="Edges", position=2, minutes=15
        );
        traversal = applied +>:HasLesson:+> Lesson(
            title="Traversal", position=1, minutes=20
        );
        optimization = applied +>:HasLesson:+> Lesson(
            title="Optimization", position=2, minutes=25
        );
        edges +>:Requires:+> nodes;
        traversal +>:Requires:+> edges;
        optimization +>:Requires:+> traversal;
        report {"ok": True, "created": True};
    }
}

walker LearningDashboard {
    has courses: list[dict] = [],
        enrollments: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Course]];
        visit [-->[?:Enrollment]];
    }
    can course with Course entry {
        modules = [];
        for module in [here->:HasModule:->[?:Module]] {
            lessons = [];
            for lesson in [module->:HasLesson:->[?:Lesson]] {
                lessons.append(
                    {
                        "id": jid(lesson),
                        "title": lesson.title,
                        "position": lesson.position,
                        "minutes": lesson.minutes,
                        "requires": [
                            jid(item) for item in [lesson->:Requires:->[?:Lesson]]
                        ]
                    }
                );
            }
            modules.append(
                {
                    "id": jid(module),
                    "title": module.title,
                    "position": module.position,
                    "lessons": lessons
                }
            );
        }
        self.courses.append({"id": jid(here), "title": here.title, "modules": modules});
    }

    can enrollment with Enrollment entry {
        self.enrollments.append(_enrollment_view(here));
    }
    can finish with Root exit {
        report {"courses": self.courses, "enrollments": self.enrollments};
    }
}

walker Enroll {
    has course_id: str,
        learner: str;

    can enroll with Root entry {
        course = jobj(self.course_id);
        if not _owned_course(course) or not self.learner.strip() {
            report {
                "ok": False,
                "error": "Select an available course and enter a learner name"
            };
            return;
        }
        for enrollment in [-->[?:Enrollment]] {
            if enrollment.learner == self.learner.strip()
                and self.course_id
                    in [jid(item) for item in [enrollment->:EnrolledIn:->[?:Course]]] {
                report {
                    "ok": True,
                    "created": False,
                    "enrollment": _enrollment_view(enrollment)
                };
                return;
            }
        }
        enrollment = here ++> Enrollment(learner=self.learner.strip());
        enrollment +>:EnrolledIn:+> course;
        report {
            "ok": True,
            "created": True,
            "enrollment": _enrollment_view(enrollment)
        };
    }
}

walker CompleteLesson {
    has enrollment_id: str,
        lesson_id: str;

    can complete with Root entry {
        enrollment = jobj(self.enrollment_id);
        lesson = jobj(self.lesson_id);
        if not isinstance(enrollment, Enrollment)
            or not isinstance(lesson, Lesson)
            or jid(enrollment) not in [jid(item) for item in [-->[?:Enrollment]]] {
            report {
                "ok": False,
                "error": "Enrollment or lesson is not available to this user"
            };
            return;
        }
        course = [enrollment->:EnrolledIn:->[?:Course]][0];
        if self.lesson_id not in [jid(item) for item in _course_lessons(course)] {
            report {"ok": False, "error": "Lesson must belong to the enrolled course"};
            return;
        }
        completed = [];
        for completion in [enrollment->:HasCompletion:->[?:Completion]] {
            completed.extend(
                [jid(item) for item in [completion->:ForLesson:->[?:Lesson]]]
            );
        }
        if self.lesson_id in completed {
            report {
                "ok": True,
                "created": False,
                "enrollment": _enrollment_view(enrollment)
            };
            return;
        }
        if any(
            jid(item) not in completed for item in [lesson->:Requires:->[?:Lesson]]
        ) {
            report {
                "ok": False,
                "error": "Complete every prerequisite before this lesson"
            };
            return;
        }
        completion = enrollment +>:HasCompletion:+> Completion(
            sequence=len(completed) + 1
        );
        completion +>:ForLesson:+> lesson;
        report {
            "ok": True,
            "created": True,
            "enrollment": _enrollment_view(enrollment)
        };
    }
}

walker AddLesson {
    has module_id: str,
        title: str,
        minutes: int,
        prerequisite_id: str = "";

    can add with Root entry {
        module = jobj(self.module_id);
        if not isinstance(module, Module) {
            report {"ok": False, "error": "Module is not available"};
            return;
        }
        courses = [module<-:HasModule:<-[?:Course]];
        if not courses or not _owned_course(courses[0]) {
            report {"ok": False, "error": "Module is not available to this user"};
            return;
        }
        if not self.title.strip() or self.minutes < 1 or self.minutes > 240 {
            report {
                "ok": False,
                "error": "Enter a lesson title and duration from 1 to 240 minutes"
            };
            return;
        }
        prerequisite = jobj(self.prerequisite_id) if self.prerequisite_id else None;
        if self.prerequisite_id
            and self.prerequisite_id
                not in [jid(item) for item in _course_lessons(courses[0])] {
            report {"ok": False, "error": "Prerequisite must belong to this course"};
            return;
        }
        lesson = module +>:HasLesson:+> Lesson(
            title=self.title.strip(),
            position=len([module->:HasLesson:->[?:Lesson]]) + 1,
            minutes=self.minutes
        );
        if prerequisite is not None {
            lesson +>:Requires:+> prerequisite;
        }
        report {"ok": True, "lesson_id": jid(lesson)};
    }
}
