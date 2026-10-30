"""Four-team elimination brackets with immutable scores and winner propagation."""
import from typing { cast }
node Tournament {
    has name: str;
}
node Team {
    has name: str;
}
node Round {
    has number: int;
}
node Match {
    has position: int,
        winner: str = "";
}
node Result {
    has home_score: int,
        away_score: int;
}
edge HasRound {}
edge HasMatch {}
edge Home {}
edge Away {}
edge AdvancesTo {}
edge HasResult {}
def _tournament(t: object) -> bool {
    return isinstance(t, Tournament)
        and jid(t) in [jid(x) for x in [root-->[?:Tournament]]];
}
def _match(m: object) -> bool {
    return isinstance(m, Match)
        and any(
            _tournament(t) for r in [m<-:HasMatch:<-[?:Round]]
            for t in [r<-:HasRound:<-[?:Tournament]]
        );
}
def _bracket(name: str) -> Tournament {
    t = root ++> Tournament(name=name);
    semi = t +>:HasRound:+> Round(number=1);
    final = t +>:HasRound:+> Round(number=2);
    f = final +>:HasMatch:+> Match(position=1);
    teams = [root-->[?:Team]];
    for i in range(2) {
        m = semi +>:HasMatch:+> Match(position=i + 1);
        m +>:Home:+> teams[i * 2];
        m +>:Away:+> teams[i * 2 + 1];
        m +>:AdvancesTo:+> f;
    }
    return t;
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Tournament]] {
            report {"ok": True};
            return;
        }
        for name in ["Aster", "Birch", "Cedar", "Delta"] {
            here ++> Team(name=name);
        }
        _bracket("Research cup " + str(self.seed));
        report {"ok": True};
    }
}

walker BracketBoard {
    has tournaments: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Tournament]];
    }
    can tournament with Tournament entry {
        rounds = [];
        for r in [here->:HasRound:->[?:Round]] {
            matches = [];
            for m in [r->:HasMatch:->[?:Match]] {
                home = [m->:Home:->[?:Team]];
                away = [m->:Away:->[?:Team]];
                matches.append(
                    {
                        "id": jid(m),
                        "position": m.position,
                        "winner": m.winner,
                        "home": home[0].name if home else "pending",
                        "away": away[0].name if away else "pending",
                        "results": [
                            {"home": s.home_score, "away": s.away_score}
                            for s in [m->:HasResult:->[?:Result]]
                        ]
                    }
                );
            }
            rounds.append({"number": r.number, "matches": matches});
        }
        self.tournaments.append({"id": jid(here), "name": here.name, "rounds": rounds});
    }
    can finish with Root exit {
        report {"tournaments": self.tournaments};
    }
}

walker CreateTournament {
    has name: str;

    can create with Root entry {
        if not self.name.strip() {
            report {"ok": False, "error": "Enter a tournament name"};
            return;
        }
        t = _bracket(self.name.strip());
        report {"ok": True, "tournament_id": jid(t)};
    }
}

walker ScoreMatch {
    has match_id: str,
        home_score: int,
        away_score: int;

    can score with Root entry {
        m = jobj(self.match_id);
        if not _match(m) {
            report {"ok": False, "error": "Match is not available"};
            return;
        }
        m = cast(Match, m);
        home = [m->:Home:->[?:Team]];
        away = [m->:Away:->[?:Team]];
        if m.winner
            or not home
            or not away
            or min(self.home_score, self.away_score) < 0
            or self.home_score == self.away_score {
            report {
                "ok": False,
                "error": "Both participants and a non-tied unrecorded score are required"
            };
            return;
        }
        winner = home[0] if self.home_score > self.away_score else away[0];
        m.winner = winner.name;
        m +>:HasResult:+> Result(
            home_score=self.home_score, away_score=self.away_score
        );
        for target in [m->:AdvancesTo:->[?:Match]] {
            if m.position == 1 {
                target +>:Home:+> winner;
            } else {
                target +>:Away:+> winner;
            }
        }
        report {"ok": True};
    }
}
