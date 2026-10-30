"""IssueDesk: project issues with assignments, comments and blocking dependencies."""

import from jaclang { JacRuntimeInterface as Jac }
import from typing { cast }

node Project {
    has name: str;
}
node Engineer {
    has name: str,
        active: bool = True;
}
node Issue {
    has title: str,
        priority: int = 3,
        status: str = "open";
}
node Comment {
    has body: str,
        sequence: int;
}
edge HasIssue {}
edge HasEngineer {}
edge AssignedTo {}
edge HasComment {}
edge Blocks {}

def _owned_project(project: any) -> bool {
    return isinstance(project, Project)
        and jid(project) in [jid(p) for p in [root-->[?:Project]]];
}

def _owned_issue(issue: any) -> bool {
    if not isinstance(issue, Issue) {
        return False;
    }
    return any(_owned_project(project) for project in [issue<-:HasIssue:<-[?:Project]]);
}

def _issue_view(issue: Issue) -> dict {
    return {
        "id": jid(issue),
        "title": issue.title,
        "priority": issue.priority,
        "status": issue.status,
        "assignees": [
            {"id": jid(engineer), "name": engineer.name}
            for engineer in [issue->:AssignedTo:->[?:Engineer]]
        ],
        "blockers": [
            {"id": jid(blocker), "title": blocker.title, "status": blocker.status}
            for blocker in [issue<-:Blocks:<-[?:Issue]]
        ],
        "comments": [
            {"id": jid(comment), "body": comment.body, "sequence": comment.sequence}
            for comment in [issue->:HasComment:->[?:Comment]]
        ]
    };
}

walker Seed {
    has seed: int = 42;

    can initialize with Root entry {
        existing = [-->[?:Project]];
        if existing {
            report {"ok": True, "project_id": jid(existing[0]), "created": False};
            return;
        }
        project = here ++> Project(name="TTG Runtime");
        avery = project +>:HasEngineer:+> Engineer(name="Avery");
        project +>:HasEngineer:+> Engineer(name="Morgan");
        blocker = project +>:HasIssue:+> Issue(
            title="Implement parser fix", priority=1 + self.seed % 3
        );
        release = project +>:HasIssue:+> Issue(
            title="Ship runtime release", priority=2
        );
        blocker +>:Blocks:+> release;
        blocker +>:AssignedTo:+> avery;
        blocker +>:HasComment:+> Comment(
            body="Reproduce the parser failure before changing the compiler.",
            sequence=1
        );
        report {"ok": True, "project_id": jid(project), "created": True};
    }
}

walker ProjectBoard {
    has projects: list[dict] = [],
        engineers: list[dict] = [],
        issues: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Project]];
    }
    can project with Project entry {
        self.projects.append({"id": jid(here), "name": here.name});
        visit [->:HasEngineer:->[?:Engineer]];
        visit [->:HasIssue:->[?:Issue]];
    }

    can engineer with Engineer entry {
        self.engineers.append(
            {"id": jid(here), "name": here.name, "active": here.active}
        );
    }
    can issue with Issue entry {
        self.issues.append(_issue_view(here));
    }
    can finish with Root exit {
        report {
            "projects": self.projects,
            "engineers": self.engineers,
            "issues": self.issues
        };
    }
}

walker CreateIssue {
    has project_id: str,
        title: str,
        priority: int = 3;

    can create with Root entry {
        project = jobj(self.project_id);
        if not _owned_project(project) {
            report {"ok": False, "error": "Project is not available to this user"};
            return;
        }
        project = cast(Project, project);
        if not self.title.strip() or self.priority < 1 or self.priority > 5 {
            report {"ok": False, "error": "Enter a title and priority from 1 to 5"};
            return;
        }
        issue = project +>:HasIssue:+> Issue(
            title=self.title.strip(), priority=self.priority
        );
        report {"ok": True, "issue": _issue_view(issue)};
    }
}

walker AssignIssue {
    has issue_id: str,
        engineer_id: str;

    can assign with Root entry {
        issue = jobj(self.issue_id);
        engineer = jobj(self.engineer_id);
        if not _owned_issue(issue)
            or not isinstance(engineer, Engineer)
            or not engineer.active {
            report {
                "ok": False,
                "error": "Select an available issue and active engineer"
            };
            return;
        }
        issue = cast(Issue, issue);
        engineer = cast(Engineer, engineer);
        project = [issue<-:HasIssue:<-[?:Project]][0];
        if jid(engineer)
            not in [jid(person) for person in [project->:HasEngineer:->[?:Engineer]]] {
            report {
                "ok": False,
                "error": "Engineer must belong to the issue's project"
            };
            return;
        }
        for existing in [edge issue->:AssignedTo:->] {
            del existing;
        }
        issue +>:AssignedTo:+> engineer;
        report {"ok": True, "issue": _issue_view(issue)};
    }
}

walker CommentIssue {
    has issue_id: str,
        body: str;

    can comment with Root entry {
        issue = jobj(self.issue_id);
        if not _owned_issue(issue) or not self.body.strip() {
            report {
                "ok": False,
                "error": "Select an available issue and enter a comment"
            };
            return;
        }
        issue = cast(Issue, issue);
        sequence = len([issue->:HasComment:->[?:Comment]]) + 1;
        issue +>:HasComment:+> Comment(body=self.body.strip(), sequence=sequence);
        report {"ok": True, "issue": _issue_view(issue)};
    }
}

walker ReachIssue {
    has target_id: str,
        found: bool = False,
        seen: set[str] = set();

    can inspect with Issue entry {
        if jid(here) in self.seen {
            return;
        }
        self.seen.add(jid(here));
        if jid(here) == self.target_id {
            self.found = True;
            disengage;
        }
        visit [->:Blocks:->[?:Issue]];
    }
}

walker BlockIssue {
    has issue_id: str,
        blocker_id: str;

    can block with Root entry {
        issue = jobj(self.issue_id);
        blocker = jobj(self.blocker_id);
        if not _owned_issue(issue) or not _owned_issue(blocker) {
            report {"ok": False, "error": "Both issues must belong to this user"};
            return;
        }
        issue = cast(Issue, issue);
        blocker = cast(Issue, blocker);
        if issue.status == "closed" {
            report {"ok": False, "error": "Reopen the issue before adding a blocker"};
            return;
        }
        reach = ReachIssue(target_id=jid(blocker));
        issue spawn reach;
        if reach.found {
            report {
                "ok": False,
                "error": "A blocking dependency cannot create a cycle"
            };
            return;
        }
        if jid(blocker) not in [jid(item) for item in [issue<-:Blocks:<-[?:Issue]]] {
            blocker +>:Blocks:+> issue;
        }
        report {"ok": True, "issue": _issue_view(issue)};
    }
}

walker CloseIssue {
    has issue_id: str;

    can close with Root entry {
        issue = jobj(self.issue_id);
        if not _owned_issue(issue) {
            report {"ok": False, "error": "Issue is not available to this user"};
            return;
        }
        issue = cast(Issue, issue);
        blockers = [
            item
            for item in [issue<-:Blocks:<-[?:Issue]]
            if item.status != "closed"
        ];
        if blockers {
            report {
                "ok": False,
                "error": "Close all blocking issues before closing this issue",
                "blockers": [item.title for item in blockers]
            };
            return;
        }
        issue.status = "closed";
        report {"ok": True, "issue": _issue_view(issue)};
    }
}

walker ReopenIssue {
    has issue_id: str;

    can reopen with Root entry {
        issue = jobj(self.issue_id);
        if not _owned_issue(issue) {
            report {"ok": False, "error": "Issue is not available to this user"};
            return;
        }
        issue = cast(Issue, issue);
        closed_dependents = [
            item
            for item in [issue->:Blocks:->[?:Issue]]
            if item.status == "closed"
        ];
        if closed_dependents {
            report {"ok": False, "error": "Reopen closed dependent issues first"};
            return;
        }
        issue.status = "open";
        report {"ok": True, "issue": _issue_view(issue)};
    }
}
