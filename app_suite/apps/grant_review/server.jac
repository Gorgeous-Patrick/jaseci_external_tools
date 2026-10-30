"""Conflict-aware reviewer assignments and independent proposal score aggregation."""
import from typing { cast }
node Proposal {
    has title: str,
        released: bool = False;
}
node Reviewer {
    has name: str;
}
node Assignment {
    has submitted: bool = False;
}
node Review {
    has merit: int,
        feasibility: int;
}
edge Conflict {}
edge HasAssignment {}
edge ReviewerRef {}
edge HasReview {}
def _proposal(p: object) -> bool {
    return isinstance(p, Proposal)
        and jid(p) in [jid(x) for x in [root-->[?:Proposal]]];
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Proposal]] {
            report {"ok": True};
            return;
        }
        p = here ++> Proposal(title="Graph storage study");
        here ++> Proposal(title="Compiler verification");
        a = here ++> Reviewer(name="Alex");
        here ++> Reviewer(name="Blair");
        here ++> Reviewer(name="Cameron");
        a +>:Conflict:+> p;
        report {"ok": True, "seed": self.seed};
    }
}

walker ReviewBoard {
    has proposals: list[dict] = [],
        reviewers: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Proposal]];
        visit [-->[?:Reviewer]];
    }
    can reviewer with Reviewer entry {
        self.reviewers.append(
            {
                "id": jid(here),
                "name": here.name,
                "conflicts": [jid(p) for p in [here->:Conflict:->[?:Proposal]]]
            }
        );
    }
    can proposal with Proposal entry {
        assignments = [];
        total = 0;
        count = 0;
        for a in [here->:HasAssignment:->[?:Assignment]] {
            r = [a->:ReviewerRef:->[?:Reviewer]][0];
            scores = [
                v.merit * 2 + v.feasibility for v in [a->:HasReview:->[?:Review]]
            ];
            assignments.append(
                {
                    "id": jid(a),
                    "reviewer": r.name,
                    "submitted": a.submitted,
                    "scores": scores
                }
            );
            if scores {
                total += scores[0];
                count += 1;
            }
        }
        self.proposals.append(
            {
                "id": jid(here),
                "title": here.title,
                "released": here.released,
                "assignments": assignments,
                "score_total": total,
                "review_count": count
            }
        );
    }

    can finish with Root exit {
        report {"proposals": self.proposals, "reviewers": self.reviewers};
    }
}

walker AssignReviewer {
    has proposal_id: str,
        reviewer_id: str;

    can assign with Root entry {
        p = jobj(self.proposal_id);
        r = jobj(self.reviewer_id);
        if not _proposal(p)
            or not isinstance(r, Reviewer)
            or self.reviewer_id not in [jid(x) for x in [-->[?:Reviewer]]] {
            report {"ok": False, "error": "Proposal or reviewer is not available"};
            return;
        }
        p = cast(Proposal, p);
        if p.released
            or self.proposal_id in [jid(x) for x in [r->:Conflict:->[?:Proposal]]]
            or any(
                self.reviewer_id in [jid(x) for x in [a->:ReviewerRef:->[?:Reviewer]]]
                for a in [p->:HasAssignment:->[?:Assignment]]
            ) {
            report {
                "ok": False,
                "error": "Released proposals, conflicts or duplicate assignments prevent assignment"
            };
            return;
        }
        a = p +>:HasAssignment:+> Assignment();
        a +>:ReviewerRef:+> r;
        report {"ok": True, "assignment_id": jid(a)};
    }
}

walker SubmitReview {
    has assignment_id: str,
        merit: int,
        feasibility: int;

    can submit with Root entry {
        a = jobj(self.assignment_id);
        if not isinstance(a, Assignment)
            or not any(_proposal(p) for p in [a<-:HasAssignment:<-[?:Proposal]]) {
            report {"ok": False, "error": "Assignment is not available"};
            return;
        }
        p = [a<-:HasAssignment:<-[?:Proposal]][0];
        if a.submitted
            or p.released
            or min(self.merit, self.feasibility) < 1
            or max(self.merit, self.feasibility) > 5 {
            report {"ok": False, "error": "Submit one review with scores from 1 to 5"};
            return;
        }
        a +>:HasReview:+> Review(merit=self.merit, feasibility=self.feasibility);
        a.submitted = True;
        report {"ok": True};
    }
}

walker ReleaseProposal {
    has proposal_id: str;

    can release with Root entry {
        p = jobj(self.proposal_id);
        if not _proposal(p) {
            report {"ok": False, "error": "Proposal is not available"};
            return;
        }
        p = cast(Proposal, p);
        assignments = [p->:HasAssignment:->[?:Assignment]];
        if p.released
            or len(assignments) < 2
            or not all(a.submitted for a in assignments) {
            report {
                "ok": False,
                "error": "Complete at least two independent reviews before release"
            };
            return;
        }
        p.released = True;
        report {"ok": True};
    }
}
