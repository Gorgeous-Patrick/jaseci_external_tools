# ClinicQueue

ClinicQueue manages a fixed-date practitioner schedule, books appointments,
rejects overlapping bookings, cancels appointments and reuses released capacity.
Native graph: `Clinic -> HasPractitioner -> Practitioner -> OffersSlot -> Slot
-> HasAppointment -> Appointment`. Every appointment preserves its cancellation
history. Each authenticated user owns an independent clinic graph.

Seed 42 creates Riverside Clinic for 2026-11-02 with Dr. Taylor and Nurse Blake.
Dr. Taylor has 09:00 and 09:15 slots that overlap, plus 10:00. The last slot shifts
by 15 or 30 minutes for seeds 43 and 44. Nurse Blake has independent 09:00/10:00
capacity. Times use integer minutes within the fixed clinic date.

```sh
python3 app_suite/evaluate.py --apps clinic_queue --seed 42 --browser --output /tmp/clinic-queue-seed42
python3 app_suite/launch.py --state /tmp/clinic-queue-seed42 --app clinic_queue --port 18704
```

Run from external-tools with suite prerequisites. Sign in as `user_0000` using
`isolated-suite-seed-password`. Add schedule slots, enter a demo patient name,
book a slot, cancel and rebook. The backend checks every overlapping slot for the
same practitioner, so two distinct slot IDs cannot double-book that practitioner.
Different practitioners may operate at the same time.

The native oracle checks exact seed membership, duplicate/invalid schedules,
overlapping booking rejection, cancellation history, rebooking, other-practitioner
capacity and cross-user isolation. It independently compares active intervals for
overlap. Browser validation books a new slot, cancels and rebooks it; native
inspection after restart verifies both historical and active appointments.
Concurrent booking contention and real patient records are outside this synthetic
sequential workload.
