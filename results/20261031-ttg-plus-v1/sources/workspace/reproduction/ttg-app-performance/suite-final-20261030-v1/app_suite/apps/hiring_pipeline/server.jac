"""Job applications, required interview scorecards and capacity-gated offers."""
import from typing { cast }
node Job {
    has title: str,
        positions: int = 1,
        threshold: int = 8;
}
node Candidate {
    has name: str;
}
node Application {
    has status: str = "applied";
}
node Interview {
    has round: str;
}
node Scorecard {
    has score: int;
}
edge HasApplication {}
edge CandidateRef {}
edge HasInterview {}
edge HasScore {}
def _owns_job(job: object) -> bool {
    return isinstance(job, Job) and jid(job) in [jid(j) for j in [root-->[?:Job]]];
}
def _owns_app(app: object) -> bool {
    return isinstance(app, Application)
        and any(_owns_job(j) for j in [app<-:HasApplication:<-[?:Job]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Job]] {
            report {"ok": True};
            return;
        }
        here ++> Job(title="Runtime Engineer", threshold=8 + self.seed % 2);
        here ++> Job(title="Developer Advocate");
        here ++> Candidate(name="Avery");
        here ++> Candidate(name="Morgan");
        report {"ok": True};
    }
}

walker HiringBoard {
    has jobs: list[dict] = [],
        candidates: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Job]];
        visit [-->[?:Candidate]];
    }
    can candidate with Candidate entry {
        self.candidates.append({"id": jid(here), "name": here.name});
    }
    can job with Job entry {
        apps = [];
        for a in [here->:HasApplication:->[?:Application]] {
            c = [a->:CandidateRef:->[?:Candidate]][0];
            apps.append(
                {
                    "id": jid(a),
                    "candidate": c.name,
                    "status": a.status,
                    "interviews": [
                        {
                            "id": jid(i),
                            "round": i.round,
                            "scores": [s.score for s in [i->:HasScore:->[?:Scorecard]]]
                        } for i in [a->:HasInterview:->[?:Interview]]
                    ]
                }
            );
        }
        self.jobs.append(
            {
                "id": jid(here),
                "title": here.title,
                "positions": here.positions,
                "threshold": here.threshold,
                "applications": apps
            }
        );
    }

    can finish with Root exit {
        report {"jobs": self.jobs, "candidates": self.candidates};
    }
}

walker CreateCandidate {
    has name: str;

    can create with Root entry {
        if not self.name.strip() {
            report {"ok": False, "error": "Enter a candidate name"};
            return;
        }
        c = here ++> Candidate(name=self.name.strip());
        report {"ok": True, "candidate_id": jid(c)};
    }
}

walker ApplyJob {
    has job_id: str,
        candidate_id: str;

    can apply with Root entry {
        job = jobj(self.job_id);
        c = jobj(self.candidate_id);
        if not _owns_job(job)
            or not isinstance(c, Candidate)
            or self.candidate_id not in [jid(p) for p in [-->[?:Candidate]]] {
            report {"ok": False, "error": "Job or candidate is not available"};
            return;
        }
        job = cast(Job, job);
        if any(
            self.candidate_id in [jid(p) for p in [a->:CandidateRef:->[?:Candidate]]]
            for a in [job->:HasApplication:->[?:Application]]
        ) {
            report {"ok": False, "error": "Candidate already applied to this job"};
            return;
        }
        app = job +>:HasApplication:+> Application();
        app +>:CandidateRef:+> c;
        report {"ok": True, "application_id": jid(app)};
    }
}

walker ScheduleInterview {
    has application_id: str,
        round: str;

    can schedule with Root entry {
        app = jobj(self.application_id);
        if not _owns_app(app) {
            report {"ok": False, "error": "Application is not available"};
            return;
        }
        app = cast(Application, app);
        if app.status != "applied"
            or self.round not in ["technical", "collaboration"]
            or any(
                i.round == self.round for i in [app->:HasInterview:->[?:Interview]]
            ) {
            report {
                "ok": False,
                "error": "Schedule each required round once before an offer"
            };
            return;
        }
        interview = app +>:HasInterview:+> Interview(round=self.round);
        report {"ok": True, "interview_id": jid(interview)};
    }
}

walker ScoreInterview {
    has interview_id: str,
        score: int;

    can score with Root entry {
        interview = jobj(self.interview_id);
        if not isinstance(interview, Interview)
            or not any(
                _owns_app(a) for a in [interview<-:HasInterview:<-[?:Application]]
            ) {
            report {"ok": False, "error": "Interview is not available"};
            return;
        }
        if self.score < 0 or self.score > 5 or [interview->:HasScore:->[?:Scorecard]] {
            report {"ok": False, "error": "Enter one score from 0 to 5"};
            return;
        }
        interview +>:HasScore:+> Scorecard(score=self.score);
        report {"ok": True};
    }
}

walker OfferApplication {
    has application_id: str;

    can offer with Root entry {
        app = jobj(self.application_id);
        if not _owns_app(app) {
            report {"ok": False, "error": "Application is not available"};
            return;
        }
        app = cast(Application, app);
        job = [app<-:HasApplication:<-[?:Job]][0];
        candidate = [app->:CandidateRef:->[?:Candidate]][0];
        interviews = [app->:HasInterview:->[?:Interview]];
        scores = [s.score for i in interviews for s in [i->:HasScore:->[?:Scorecard]]];
        if app.status != "applied"
            or len(interviews) != 2
            or len(scores) != 2
            or sum(scores) < job.threshold {
            report {
                "ok": False,
                "error": "Complete both interview rounds and meet the score threshold"
            };
            return;
        }
        if len(
            [
                a
                for a in [job->:HasApplication:->[?:Application]]
                if a.status == "offered"
            ]
        )
            >= job.positions
            or any(
                a.status == "offered"
                for a in [candidate<-:CandidateRef:<-[?:Application]]
            ) {
            report {
                "ok": False,
                "error": "Job capacity or candidate offer exclusivity prevents this offer"
            };
            return;
        }
        app.status = "offered";
        report {"ok": True};
    }
}
