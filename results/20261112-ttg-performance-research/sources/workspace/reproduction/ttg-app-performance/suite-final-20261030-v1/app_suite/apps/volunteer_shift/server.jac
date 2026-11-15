"""Skill-matched volunteer shifts with capacity and FIFO waitlist promotion."""
import from typing { cast }
node Organization {
    has name: str;
}
node Skill {
    has name: str;
}
node Volunteer {
    has name: str;
}
node Shift {
    has name: str,
        capacity: int;
}
node Signup {
    has position: int,
        status: str;
}
edge HasSkill {}
edge HasVolunteer {}
edge HasShift {}
edge NeedsSkill {}
edge HasSignup {}
edge VolunteerRef {}
def _shift(s: object) -> bool {
    return isinstance(s, Shift)
        and any(
            jid(o) in [jid(x) for x in [root-->[?:Organization]]]
            for o in [s<-:HasShift:<-[?:Organization]]
        );
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Organization]] {
            report {"ok": True};
            return;
        }
        o = here ++> Organization(name="Campus volunteers");
        first = Skill(name="First aid");
        registration = Skill(name="Registration");
        for name in ["Avery", "Jordan", "Casey"] {
            v = o +>:HasVolunteer:+> Volunteer(name=name);
            v +>:HasSkill:+> first;
        }
        m = o +>:HasVolunteer:+> Volunteer(name="Morgan");
        m +>:HasSkill:+> registration;
        s = o +>:HasShift:+> Shift(name="Safety desk", capacity=1);
        s +>:NeedsSkill:+> first;
        r = o +>:HasShift:+> Shift(name="Registration desk", capacity=1);
        r +>:NeedsSkill:+> registration;
        report {"ok": True, "seed": self.seed};
    }
}

walker VolunteerBoard {
    has organizations: list[dict] = [],
        volunteers: list[dict] = [],
        shifts: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Organization]];
    }
    can organization with Organization entry {
        self.organizations.append({"id": jid(here), "name": here.name});
        visit [->:HasVolunteer:->[?:Volunteer]];
        visit [->:HasShift:->[?:Shift]];
    }
    can volunteer with Volunteer entry {
        self.volunteers.append(
            {
                "id": jid(here),
                "name": here.name,
                "skills": [s.name for s in [here->:HasSkill:->[?:Skill]]]
            }
        );
    }
    can shift with Shift entry {
        self.shifts.append(
            {
                "id": jid(here),
                "name": here.name,
                "capacity": here.capacity,
                "signups": [
                    {
                        "id": jid(s),
                        "position": s.position,
                        "status": s.status,
                        "volunteer": [s->:VolunteerRef:->[?:Volunteer]][0].name
                    } for s in [here->:HasSignup:->[?:Signup]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {
            "organizations": self.organizations,
            "volunteers": self.volunteers,
            "shifts": self.shifts
        };
    }
}

walker JoinShift {
    has shift_id: str,
        volunteer_id: str;

    can join with Root entry {
        s = jobj(self.shift_id);
        v = jobj(self.volunteer_id);
        if not _shift(s) or not isinstance(v, Volunteer) {
            report {"ok": False, "error": "Shift or volunteer is not available"};
            return;
        }
        s = cast(Shift, s);
        o = [s<-:HasShift:<-[?:Organization]][0];
        if self.volunteer_id not in [jid(x) for x in [o->:HasVolunteer:->[?:Volunteer]]]
            or not set(jid(x) for x in [s->:NeedsSkill:->[?:Skill]]).issubset(
                set(jid(x) for x in [v->:HasSkill:->[?:Skill]])
            ) {
            report {
                "ok": False,
                "error": "Volunteer must have the required shift skills"
            };
            return;
        }
        signups = [s->:HasSignup:->[?:Signup]];
        if any(
            a.status != "cancelled"
                and self.volunteer_id
                    in [jid(x) for x in [a->:VolunteerRef:->[?:Volunteer]]]
            for a in signups
        ) {
            report {"ok": False, "error": "Volunteer already joined this shift"};
            return;
        }
        status = "confirmed"
            if len(
                [
                    a
                    for a in signups
                    if a.status == "confirmed"
                ]
            )
                < s.capacity
            else "waitlisted";
        a = s +>:HasSignup:+> Signup(position=len(signups) + 1, status=status);
        a +>:VolunteerRef:+> v;
        report {"ok": True, "signup_id": jid(a), "status": status};
    }
}

walker CancelSignup {
    has signup_id: str;

    can cancel with Root entry {
        a = jobj(self.signup_id);
        if not isinstance(a, Signup)
            or not any(_shift(s) for s in [a<-:HasSignup:<-[?:Shift]]) {
            report {"ok": False, "error": "Signup is not available"};
            return;
        }
        if a.status == "cancelled" {
            report {"ok": False, "error": "Signup is already cancelled"};
            return;
        }
        occupied = a.status == "confirmed";
        a.status = "cancelled";
        s = [a<-:HasSignup:<-[?:Shift]][0];
        waiting = [
            x
            for x in [s->:HasSignup:->[?:Signup]]
            if x.status == "waitlisted"
        ];
        waiting.sort(key=lambda (x: Signup) { x.position; });
        if occupied and waiting {
            waiting[0].status = "confirmed";
        }
        report {"ok": True};
    }
}
