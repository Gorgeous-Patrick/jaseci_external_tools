"""ClinicQueue: practitioner schedules, overlap checks and appointment cancellation."""

import from typing { cast }

node Clinic {
    has name: str,
        date: str;
}
node Practitioner {
    has name: str,
        specialty: str;
}
node Slot {
    has start_minute: int,
        duration: int;
}
node Appointment {
    has patient: str,
        status: str = "booked";
}
edge HasPractitioner {}
edge OffersSlot {}
edge HasAppointment {}

def _clinic -> Clinic | None {
    clinics = [root-->[?:Clinic]];
    return clinics[0] if clinics else None;
}

def _owned_slot(slot: object) -> bool {
    clinic = _clinic();
    if clinic is None or not isinstance(slot, Slot) {
        return False;
    }
    practitioners = [clinic->:HasPractitioner:->[?:Practitioner]];
    return any(
        jid(person) in [jid(owner) for owner in [slot<-:OffersSlot:<-[?:Practitioner]]]
        for person in practitioners
    );
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Clinic]] {
            report {"ok": True, "created": False};
            return;
        }
        clinic = here ++> Clinic(name="Riverside Clinic", date="2026-11-02");
        doctor = clinic +>:HasPractitioner:+> Practitioner(
            name="Dr. Taylor", specialty="General practice"
        );
        nurse = clinic +>:HasPractitioner:+> Practitioner(
            name="Nurse Blake", specialty="Screening"
        );
        for start in [540, 555, 600 + self.seed % 3 * 15] {
            doctor +>:OffersSlot:+> Slot(start_minute=start, duration=30);
        }
        for start in [540, 600] {
            nurse +>:OffersSlot:+> Slot(start_minute=start, duration=20);
        }
        report {"ok": True, "created": True};
    }
}

walker ClinicSchedule {
    has clinics: list[dict] = [],
        practitioners: list[dict] = [],
        slots: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Clinic]];
    }
    can clinic with Clinic entry {
        self.clinics.append({"id": jid(here), "name": here.name, "date": here.date});
        visit [->:HasPractitioner:->[?:Practitioner]];
    }

    can practitioner with Practitioner entry {
        self.practitioners.append(
            {"id": jid(here), "name": here.name, "specialty": here.specialty}
        );
        visit [->:OffersSlot:->[?:Slot]];
    }

    can slot with Slot entry {
        owner = [here<-:OffersSlot:<-[?:Practitioner]][0];
        self.slots.append(
            {
                "id": jid(here),
                "practitioner_id": jid(owner),
                "start_minute": here.start_minute,
                "duration": here.duration,
                "appointments": [
                    {"id": jid(item), "patient": item.patient, "status": item.status}
                    for item in [here->:HasAppointment:->[?:Appointment]]
                ]
            }
        );
    }

    can finish with Root exit {
        report {
            "clinics": self.clinics,
            "practitioners": self.practitioners,
            "slots": self.slots
        };
    }
}

walker AddSlot {
    has practitioner_id: str,
        start_minute: int,
        duration: int;

    can create with Root entry {
        clinic = _clinic();
        person = jobj(self.practitioner_id);
        if clinic is None
            or not isinstance(person, Practitioner)
            or jid(person)
                not in [
                    jid(item) for item in [clinic->:HasPractitioner:->[?:Practitioner]]
                ] {
            report {"ok": False, "error": "Practitioner is not available to this user"};
            return;
        }
        if self.start_minute < 0
            or self.duration < 5
            or self.duration > 180
            or self.start_minute + self.duration > 1440 {
            report {
                "ok": False,
                "error": "Enter a valid start time and duration from 5 to 180 minutes"
            };
            return;
        }
        if any(
            item.start_minute == self.start_minute and item.duration == self.duration
            for item in [person->:OffersSlot:->[?:Slot]]
        ) {
            report {"ok": False, "error": "This schedule slot already exists"};
            return;
        }
        slot = person +>:OffersSlot:+> Slot(
            start_minute=self.start_minute, duration=self.duration
        );
        report {"ok": True, "slot_id": jid(slot)};
    }
}

walker BookAppointment {
    has slot_id: str,
        patient: str;

    can book with Root entry {
        slot = jobj(self.slot_id);
        if not _owned_slot(slot) or not self.patient.strip() {
            report {
                "ok": False,
                "error": "Select an available slot and enter a patient name"
            };
            return;
        }
        slot = cast(Slot, slot);
        practitioner = [slot<-:OffersSlot:<-[?:Practitioner]][0];
        for other in [practitioner->:OffersSlot:->[?:Slot]] {
            if slot.start_minute < other.start_minute + other.duration
                and other.start_minute < slot.start_minute + slot.duration {
                if any(
                    item.status == "booked"
                    for item in [other->:HasAppointment:->[?:Appointment]]
                ) {
                    report {
                        "ok": False,
                        "error": "Practitioner already has an overlapping appointment"
                    };
                    return;
                }
            }
        }
        appointment = slot +>:HasAppointment:+> Appointment(
            patient=self.patient.strip()
        );
        report {"ok": True, "appointment_id": jid(appointment)};
    }
}

walker CancelAppointment {
    has appointment_id: str;

    can cancel with Root entry {
        appointment = jobj(self.appointment_id);
        if not isinstance(appointment, Appointment) {
            report {"ok": False, "error": "Appointment is not available"};
            return;
        }
        slots = [appointment<-:HasAppointment:<-[?:Slot]];
        if not slots or not _owned_slot(slots[0]) {
            report {"ok": False, "error": "Appointment is not available to this user"};
            return;
        }
        if appointment.status != "booked" {
            report {"ok": False, "error": "Only booked appointments can be cancelled"};
            return;
        }
        appointment.status = "cancelled";
        report {"ok": True, "appointment_id": jid(appointment)};
    }
}
