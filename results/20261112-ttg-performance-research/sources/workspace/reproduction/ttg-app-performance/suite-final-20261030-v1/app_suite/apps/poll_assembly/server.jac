"""Eligible-voter ballots, vote changes, quorum and final motion outcomes."""
import from typing { cast }
node Assembly {
    has name: str,
        quorum: int;
}
node Motion {
    has title: str,
        status: str = "open",
        outcome: str = "pending";
}
node Option {
    has label: str;
}
node Voter {
    has name: str,
        eligible: bool = True;
}
node Ballot {}
edge HasMotion {}
edge HasOption {}
edge HasVoter {}
edge HasBallot {}
edge VoterRef {}
edge OptionRef {}
def _motion(m: object) -> bool {
    return isinstance(m, Motion)
        and any(
            jid(a) in [jid(x) for x in [root-->[?:Assembly]]]
            for a in [m<-:HasMotion:<-[?:Assembly]]
        );
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Assembly]] {
            report {"ok": True};
            return;
        }
        a = here ++> Assembly(name="Research assembly", quorum=2);
        a +>:HasVoter:+> Voter(name="Avery");
        a +>:HasVoter:+> Voter(name="Morgan");
        a +>:HasVoter:+> Voter(name="Guest", eligible=False);
        for title in ["Adopt graph policy", "Release vote"] {
            m = a +>:HasMotion:+> Motion(title=title);
            m +>:HasOption:+> Option(label="Yes");
            m +>:HasOption:+> Option(label="No");
        }
        report {"ok": True, "seed": self.seed};
    }
}

walker AssemblyBoard {
    has assemblies: list[dict] = [],
        voters: list[dict] = [],
        motions: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Assembly]];
    }
    can assembly with Assembly entry {
        self.assemblies.append(
            {"id": jid(here), "name": here.name, "quorum": here.quorum}
        );
        visit [->:HasVoter:->[?:Voter]];
        visit [->:HasMotion:->[?:Motion]];
    }
    can voter with Voter entry {
        self.voters.append(
            {"id": jid(here), "name": here.name, "eligible": here.eligible}
        );
    }
    can motion with Motion entry {
        ballots = [here->:HasBallot:->[?:Ballot]];
        self.motions.append(
            {
                "id": jid(here),
                "title": here.title,
                "status": here.status,
                "outcome": here.outcome,
                "ballot_count": len(ballots),
                "options": [
                    {
                        "id": jid(o),
                        "label": o.label,
                        "votes": len(
                            [
                                b
                                for b in ballots
                                if jid(o)
                                    in [jid(x) for x in [b->:OptionRef:->[?:Option]]]
                            ]
                        )
                    } for o in [here->:HasOption:->[?:Option]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {
            "assemblies": self.assemblies,
            "voters": self.voters,
            "motions": self.motions
        };
    }
}

walker CastBallot {
    has motion_id: str,
        voter_id: str,
        option_id: str;

    can cast_vote with Root entry {
        m = jobj(self.motion_id);
        v = jobj(self.voter_id);
        o = jobj(self.option_id);
        if not _motion(m) or not isinstance(v, Voter) or not isinstance(o, Option) {
            report {"ok": False, "error": "Motion, voter or option is not available"};
            return;
        }
        m = cast(Motion, m);
        a = [m<-:HasMotion:<-[?:Assembly]][0];
        if m.status != "open"
            or not v.eligible
            or self.voter_id not in [jid(x) for x in [a->:HasVoter:->[?:Voter]]]
            or self.option_id not in [jid(x) for x in [m->:HasOption:->[?:Option]]] {
            report {
                "ok": False,
                "error": "Only eligible voters may vote on open motions using their options"
            };
            return;
        }
        existing = [
            b
            for b in [m->:HasBallot:->[?:Ballot]]
            if self.voter_id in [jid(x) for x in [b->:VoterRef:->[?:Voter]]]
        ];
        if existing {
            ballot = existing[0];
            for e in [edge ballot->:OptionRef:->] {
                del e;
            }
        } else {
            ballot = m +>:HasBallot:+> Ballot();
            ballot +>:VoterRef:+> v;
        }
        ballot +>:OptionRef:+> o;
        report {"ok": True};
    }
}

walker CloseMotion {
    has motion_id: str;

    can close with Root entry {
        m = jobj(self.motion_id);
        if not _motion(m) {
            report {"ok": False, "error": "Motion is not available"};
            return;
        }
        m = cast(Motion, m);
        a = [m<-:HasMotion:<-[?:Assembly]][0];
        ballots = [m->:HasBallot:->[?:Ballot]];
        if m.status != "open" or len(ballots) < a.quorum {
            report {
                "ok": False,
                "error": "Quorum must be reached before closing an open motion"
            };
            return;
        }
        yes = len(
            [
                b
                for b in ballots
                if [b->:OptionRef:->[?:Option]][0].label == "Yes"
            ]
        );
        m.outcome = "passed" if yes * 2 > len(ballots) else "rejected";
        m.status = "closed";
        report {"ok": True};
    }
}
