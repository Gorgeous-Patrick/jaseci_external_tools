"""Sample volume lineage, batch assignment and repeatable quality-control release."""
import from typing { cast }
node Sample {
    has name: str,
        initial: int,
        remaining: int;
}
node Aliquot {
    has number: int,
        volume: int;
}
node Batch {
    has name: str,
        released: bool = False;
}
node Assay {
    has name: str,
        lower: int,
        upper: int;
}
node Result {
    has value: int,
        passed: bool,
        sequence: int;
}
edge HasAliquot {}
edge Includes {}
edge HasResult {}
edge AssayRef {}
def _root_owned(x: object, kind: type) -> bool {
    return isinstance(x, kind) and jid(x) in [jid(n) for n in [root-->]];
}
def _aliquot(x: object) -> bool {
    return isinstance(x, Aliquot)
        and any(_root_owned(s, Sample) for s in [x<-:HasAliquot:<-[?:Sample]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Sample]] {
            report {"ok": True};
            return;
        }
        here ++> Sample(
            name="Water sample",
            initial=100 + self.seed % 3,
            remaining=100 + self.seed % 3
        );
        here ++> Batch(name="Morning panel");
        here ++> Assay(name="Conductivity", lower=10, upper=20);
        report {"ok": True};
    }
}

walker LabBoard {
    has samples: list[dict] = [],
        batches: list[dict] = [],
        assays: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Sample]];
        visit [-->[?:Batch]];
        visit [-->[?:Assay]];
    }
    can sample with Sample entry {
        self.samples.append(
            {
                "id": jid(here),
                "name": here.name,
                "initial": here.initial,
                "remaining": here.remaining,
                "aliquots": [
                    {
                        "id": jid(a),
                        "number": a.number,
                        "volume": a.volume,
                        "assigned": bool([a<-:Includes:<-[?:Batch]]),
                        "results": [
                            {
                                "value": r.value,
                                "passed": r.passed,
                                "sequence": r.sequence
                            } for r in [a->:HasResult:->[?:Result]]
                        ]
                    } for a in [here->:HasAliquot:->[?:Aliquot]]
                ]
            }
        );
    }
    can batch with Batch entry {
        self.batches.append(
            {
                "id": jid(here),
                "name": here.name,
                "released": here.released,
                "aliquots": [jid(a) for a in [here->:Includes:->[?:Aliquot]]]
            }
        );
    }
    can assay with Assay entry {
        self.assays.append(
            {
                "id": jid(here),
                "name": here.name,
                "lower": here.lower,
                "upper": here.upper
            }
        );
    }
    can finish with Root exit {
        report {
            "samples": self.samples,
            "batches": self.batches,
            "assays": self.assays
        };
    }
}

walker SplitSample {
    has sample_id: str,
        volume: int;

    can split with Root entry {
        s = jobj(self.sample_id);
        if not _root_owned(s, Sample) {
            report {"ok": False, "error": "Sample is not available"};
            return;
        }
        s = cast(Sample, s);
        if self.volume < 1 or self.volume > s.remaining {
            report {
                "ok": False,
                "error": "Aliquot volume exceeds the remaining sample"
            };
            return;
        }
        a = s +>:HasAliquot:+> Aliquot(
            number=len([s->:HasAliquot:->[?:Aliquot]]) + 1, volume=self.volume
        );
        s.remaining -= self.volume;
        report {"ok": True, "aliquot_id": jid(a)};
    }
}

walker CreateBatch {
    has name: str;

    can create with Root entry {
        if not self.name.strip() {
            report {"ok": False, "error": "Enter a batch name"};
            return;
        }
        b = here ++> Batch(name=self.name.strip());
        report {"ok": True, "batch_id": jid(b)};
    }
}

walker AddAliquot {
    has batch_id: str,
        aliquot_id: str;

    can add with Root entry {
        b = jobj(self.batch_id);
        a = jobj(self.aliquot_id);
        if not _root_owned(b, Batch) or not _aliquot(a) {
            report {"ok": False, "error": "Batch or aliquot is not available"};
            return;
        }
        b = cast(Batch, b);
        a = cast(Aliquot, a);
        if b.released or [a<-:Includes:<-[?:Batch]] {
            report {
                "ok": False,
                "error": "Use an unassigned aliquot and unreleased batch"
            };
            return;
        }
        b +>:Includes:+> a;
        report {"ok": True};
    }
}

walker RecordResult {
    has aliquot_id: str,
        assay_id: str,
        value: int;

    can record with Root entry {
        a = jobj(self.aliquot_id);
        assay = jobj(self.assay_id);
        if not _aliquot(a) or not _root_owned(assay, Assay) {
            report {"ok": False, "error": "Aliquot or assay is not available"};
            return;
        }
        a = cast(Aliquot, a);
        assay = cast(Assay, assay);
        results = [a->:HasResult:->[?:Result]];
        if any(b.released for b in [a<-:Includes:<-[?:Batch]])
            or (results and results[-1].passed) {
            report {
                "ok": False,
                "error": "Only untested or failed unreleased aliquots may be tested"
            };
            return;
        }
        r = a +>:HasResult:+> Result(
            value=self.value,
            passed=assay.lower <= self.value and self.value <= assay.upper,
            sequence=len(results) + 1
        );
        r +>:AssayRef:+> assay;
        report {"ok": True};
    }
}

walker ReleaseBatch {
    has batch_id: str;

    can release with Root entry {
        b = jobj(self.batch_id);
        if not _root_owned(b, Batch) {
            report {"ok": False, "error": "Batch is not available"};
            return;
        }
        b = cast(Batch, b);
        aliquots = [b->:Includes:->[?:Aliquot]];
        if b.released or not aliquots {
            report {"ok": False, "error": "A nonempty unreleased batch is required"};
            return;
        }
        for a in aliquots {
            results = [a->:HasResult:->[?:Result]];
            if not results or not results[-1].passed {
                report {
                    "ok": False,
                    "error": "Every aliquot must pass its latest quality-control test"
                };
                return;
            }
        }
        b.released = True;
        report {"ok": True};
    }
}
