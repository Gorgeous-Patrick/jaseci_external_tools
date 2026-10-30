"""Domain-specific native correctness oracles for full application workflows."""
from native import write_json


class Scenario:
    def __init__(self, server, token, directory):
        self.server, self.token, self.directory = server, token, directory
        self.steps = []

    def call(self, name, body=None, accepted=True, read=False):
        result = self.server.walker(name, body or {}, self.token)[0]
        if not read:
            assert result['ok'] is accepted, f'{name}: expected acceptance={accepted}: {result}'
        self.steps.append({'walker': name, 'input': body or {}, 'expected_accepted': accepted,
                           'actual': result, 'passed': True})
        write_json(self.directory / 'native-steps.json', self.steps)
        return result

    def assert_private(self, read_walker, collection, mutation, body):
        password = 'isolated-suite-seed-password'
        self.server.post('/user/register', {'identities': [{'type': 'username', 'value': 'other_user'}],
                                            'credential': {'type': 'password', 'password': password}})
        token = self.server.post('/user/login', {'identity': {'type': 'username', 'value': 'other_user'},
                                                'credential': {'type': 'password', 'password': password}})['token']
        assert self.server.walker(read_walker, {}, token)[0][collection] == []
        assert self.server.walker(mutation, body, token)[0]['ok'] is False

    def finish(self, read_walker):
        board = self.call(read_walker, read=True)
        return {'native_steps': len(self.steps), 'expected_board': board,
                'read_walker': read_walker, 'permission_check': 'passed'}


def approval_desk(server, token, seed, directory):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    initial = case.call('ExpenseBoard', read=True)
    assert len(initial['expenses']) == 1
    low = initial['expenses'][0]
    assert low['title'] == 'Conference travel' and low['status'] == 'draft'
    assert [(line['description'], line['quantity'], line['unit_cents']) for line in low['lines']] == [
        ('Rail ticket', 1, 10000 + seed % 3 * 1000), ('Registration', 1, 5000)]
    case.call('Seed', {'seed': seed})
    assert case.call('ExpenseBoard', read=True) == initial
    case.call('PayExpense', {'expense_id': low['id']}, False)
    submitted = case.call('SubmitExpense', {'expense_id': low['id']})['expense']
    assert submitted['total_cents'] == 15000 + seed % 3 * 1000
    assert [step['role'] for step in submitted['steps']] == ['manager']
    case.call('DecideApproval', {'step_id': submitted['steps'][0]['id'], 'approve': True})
    paid = case.call('PayExpense', {'expense_id': low['id']})['expense']
    assert paid['status'] == 'paid' and len(paid['payments']) == 1
    assert paid['payments'][0]['amount_cents'] == 15000 + seed % 3 * 1000
    case.call('PayExpense', {'expense_id': low['id']}, False)
    case.call('CreateExpense', {'title': ' '}, False)
    high = case.call('CreateExpense', {'title': 'Equipment purchase'})['expense']
    case.call('SubmitExpense', {'expense_id': high['id']}, False)
    case.call('AddLineItem', {'expense_id': high['id'], 'description': 'Workstation', 'quantity': 0, 'unit_cents': 30000}, False)
    case.call('AddLineItem', {'expense_id': high['id'], 'description': 'Workstation', 'quantity': 2, 'unit_cents': 30000})
    high = case.call('SubmitExpense', {'expense_id': high['id']})['expense']
    assert high['total_cents'] == 60000
    assert [(step['position'], step['role']) for step in high['steps']] == [(1, 'manager'), (2, 'finance')]
    case.call('AddLineItem', {'expense_id': high['id'], 'description': 'Extra', 'quantity': 1, 'unit_cents': 100}, False)
    case.call('SubmitExpense', {'expense_id': high['id']}, False)
    case.call('DecideApproval', {'step_id': high['steps'][1]['id'], 'approve': True}, False)
    case.call('DecideApproval', {'step_id': high['steps'][0]['id'], 'approve': True})
    case.call('PayExpense', {'expense_id': high['id']}, False)
    high = case.call('DecideApproval', {'step_id': high['steps'][1]['id'], 'approve': True})['expense']
    assert high['status'] == 'approved'
    paid_high = case.call('PayExpense', {'expense_id': high['id']})['expense']
    assert len(paid_high['payments']) == 1 and paid_high['payments'][0]['amount_cents'] == 60000
    rejected = case.call('CreateExpense', {'title': 'Rejected travel'})['expense']
    case.call('AddLineItem', {'expense_id': rejected['id'], 'description': 'Invalid trip', 'quantity': 1, 'unit_cents': 100})
    rejected = case.call('SubmitExpense', {'expense_id': rejected['id']})['expense']
    rejected = case.call('DecideApproval', {'step_id': rejected['steps'][0]['id'], 'approve': False})['expense']
    assert rejected['status'] == 'rejected' and rejected['payments'] == []
    case.call('PayExpense', {'expense_id': rejected['id']}, False)
    case.assert_private('ExpenseBoard', 'expenses', 'PayExpense', {'expense_id': high['id']})
    result = case.finish('ExpenseBoard')
    assert sorted(row['status'] for row in result['expected_board']['expenses']) == ['paid', 'paid', 'rejected']
    assert sum(payment['amount_cents'] for row in result['expected_board']['expenses'] for payment in row['payments']) == 75000 + seed % 3 * 1000
    return result


def stock_room(server, token, seed, directory):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    initial = case.call('Inventory', read=True)
    assert len(initial['warehouses']) == 1 and initial['warehouses'][0]['name'] == 'Research Store'
    assert sorted(row['code'] for row in initial['skus']) == ['CAB-01', 'SEN-01']
    sensor = next(row['id'] for row in initial['skus'] if row['name'] == 'Sensor')
    initial_units = 12 + seed % 3
    assert sum(row['received'] for row in initial['lots'] if row['sku_id'] == sensor) == initial_units
    case.call('Seed', {'seed': seed})
    assert case.call('Inventory', read=True) == initial

    def conserve(board):
        # Independently reconstruct active reservations from allocation records.
        reserved = {}
        dispatched = {}
        for reservation in board['reservations']:
            assert sum(item['quantity'] for item in reservation['allocations']) == reservation['quantity']
            for item in reservation['allocations']:
                target = reserved if reservation['status'] == 'reserved' else dispatched if reservation['status'] == 'dispatched' else None
                if target is not None:
                    target[item['lot_id']] = target.get(item['lot_id'], 0) + item['quantity']
        for lot in board['lots']:
            assert min(lot['available'], lot['dispatched']) >= 0
            assert lot['dispatched'] == dispatched.get(lot['id'], 0)
            assert lot['received'] == lot['available'] + lot['dispatched'] + reserved.get(lot['id'], 0)
        assert sum(item['quantity'] for item in board['dispatches']) == sum(lot['dispatched'] for lot in board['lots'])

    conserve(initial)
    case.call('ReceiveStock', {'sku_id': sensor, 'quantity': 0}, False)
    case.call('ReserveStock', {'sku_id': sensor, 'quantity': 999, 'reference': 'Too much'}, False)
    assert case.call('Inventory', read=True) == initial, 'Rejected reservations must not partially allocate'
    first = case.call('ReserveStock', {'sku_id': sensor, 'quantity': 8, 'reference': 'ORDER-RELEASE'})['reservation']
    assert [(row['sequence'], row['quantity']) for row in first['allocations']] == [(1, 5 + seed % 3), (2, 3 - seed % 3)]
    conserve(case.call('Inventory', read=True))
    case.call('ReserveStock', {'sku_id': sensor, 'quantity': 1, 'reference': 'ORDER-RELEASE'}, False)
    case.call('ReleaseReservation', {'reservation_id': first['id']})
    case.call('ReleaseReservation', {'reservation_id': first['id']}, False)
    case.call('DispatchReservation', {'reservation_id': first['id']}, False)
    restored = case.call('Inventory', read=True)
    conserve(restored)
    assert sum(row['available'] for row in restored['lots'] if row['sku_id'] == sensor) == initial_units
    shipment = case.call('ReserveStock', {'sku_id': sensor, 'quantity': 8, 'reference': 'ORDER-SHIP'})['reservation']
    case.call('DispatchReservation', {'reservation_id': shipment['id']})
    case.call('DispatchReservation', {'reservation_id': shipment['id']}, False)
    case.call('ReleaseReservation', {'reservation_id': shipment['id']}, False)
    case.call('ReceiveStock', {'sku_id': sensor, 'quantity': 6})
    active = case.call('ReserveStock', {'sku_id': sensor, 'quantity': 3, 'reference': 'ORDER-ACTIVE'})['reservation']
    conserved = case.call('Inventory', read=True)
    conserve(conserved)
    assert sum(row['received'] for row in conserved['lots'] if row['sku_id'] == sensor) == initial_units + 6
    assert sum(row['available'] for row in conserved['lots'] if row['sku_id'] == sensor) == initial_units - 5
    case.assert_private('Inventory', 'warehouses', 'ReleaseReservation', {'reservation_id': active['id']})
    result = case.finish('Inventory')
    assert result['expected_board'] == conserved
    return result


def clinic_queue(server, token, seed, directory):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    initial = case.call('ClinicSchedule', read=True)
    assert len(initial['clinics']) == 1 and initial['clinics'][0]['date'] == '2026-11-02'
    assert len(initial['slots']) == 5
    doctor = next(row['id'] for row in initial['practitioners'] if row['name'] == 'Dr. Taylor')
    nurse = next(row['id'] for row in initial['practitioners'] if row['name'] == 'Nurse Blake')
    get_slot = lambda person, start: next(row['id'] for row in initial['slots'] if row['practitioner_id'] == person and row['start_minute'] == start)
    first, overlap, separate = get_slot(doctor, 540), get_slot(doctor, 555), get_slot(nurse, 540)
    case.call('Seed', {'seed': seed})
    assert case.call('ClinicSchedule', read=True) == initial
    case.call('BookAppointment', {'slot_id': first, 'patient': ' '}, False)
    alice = case.call('BookAppointment', {'slot_id': first, 'patient': 'Alice Demo'})['appointment_id']
    case.call('BookAppointment', {'slot_id': first, 'patient': 'Duplicate Demo'}, False)
    case.call('BookAppointment', {'slot_id': overlap, 'patient': 'Overlap Demo'}, False)
    case.call('BookAppointment', {'slot_id': separate, 'patient': 'Bob Demo'})
    case.call('CancelAppointment', {'appointment_id': alice})
    case.call('CancelAppointment', {'appointment_id': alice}, False)
    charlie = case.call('BookAppointment', {'slot_id': overlap, 'patient': 'Charlie Demo'})['appointment_id']
    case.call('BookAppointment', {'slot_id': first, 'patient': 'Still overlapping'}, False)
    case.call('CancelAppointment', {'appointment_id': charlie})
    rebooked = case.call('BookAppointment', {'slot_id': first, 'patient': 'Dana Demo'})['appointment_id']
    case.call('AddSlot', {'practitioner_id': doctor, 'start_minute': 1440, 'duration': 30}, False)
    case.call('AddSlot', {'practitioner_id': doctor, 'start_minute': 540, 'duration': 30}, False)
    case.call('AddSlot', {'practitioner_id': doctor, 'start_minute': 660, 'duration': 30})
    case.assert_private('ClinicSchedule', 'clinics', 'CancelAppointment', {'appointment_id': rebooked})
    result = case.finish('ClinicSchedule')
    assert len(result['expected_board']['slots']) == 6
    for person in result['expected_board']['practitioners']:
        booked = [row for row in result['expected_board']['slots'] if row['practitioner_id'] == person['id']
                  and any(item['status'] == 'booked' for item in row['appointments'])]
        for i, left in enumerate(booked):
            assert len([item for item in left['appointments'] if item['status'] == 'booked']) == 1
            for right in booked[i+1:]:
                assert left['start_minute'] + left['duration'] <= right['start_minute'] or right['start_minute'] + right['duration'] <= left['start_minute']
    return result


def course_path(server, token, seed, directory):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    initial = case.call('LearningDashboard', read=True)
    assert len(initial['courses']) == 1 and initial['courses'][0]['title'] == 'Graph Systems'
    course = initial['courses'][0]
    lessons = {row['title']: row for module in course['modules'] for row in module['lessons']}
    assert set(lessons) == {'Nodes', 'Edges', 'Traversal', 'Optimization'}
    assert lessons['Nodes']['minutes'] == 10 + seed % 3
    assert lessons['Edges']['requires'] == [lessons['Nodes']['id']]
    case.call('Seed', {'seed': seed})
    assert case.call('LearningDashboard', read=True) == initial
    case.call('Enroll', {'course_id': course['id'], 'learner': ' '}, False)
    alice = case.call('Enroll', {'course_id': course['id'], 'learner': 'Alice Learner'})['enrollment']
    duplicate = case.call('Enroll', {'course_id': course['id'], 'learner': 'Alice Learner'})
    assert duplicate['created'] is False and duplicate['enrollment']['id'] == alice['id']
    case.call('CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lessons['Traversal']['id']}, False)
    case.call('CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lessons['Nodes']['id']})
    duplicate = case.call('CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lessons['Nodes']['id']})
    assert duplicate['created'] is False and len(duplicate['enrollment']['completed']) == 1
    case.call('CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lessons['Edges']['id']})
    bob = case.call('Enroll', {'course_id': course['id'], 'learner': 'Bob Learner'})['enrollment']
    case.call('CompleteLesson', {'enrollment_id': bob['id'], 'lesson_id': lessons['Edges']['id']}, False)
    case.call('CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lessons['Traversal']['id']})
    completed = case.call('CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lessons['Optimization']['id']})['enrollment']
    assert len(completed['completed']) == completed['total_lessons'] == 4
    module = next(row for row in course['modules'] if row['title'] == 'Applied Traversal')
    case.call('AddLesson', {'module_id': module['id'], 'title': 'Invalid duration', 'minutes': 0}, False)
    lesson = case.call('AddLesson', {'module_id': module['id'], 'title': 'Checkpoint reasoning', 'minutes': 30,
                                   'prerequisite_id': lessons['Optimization']['id']})['lesson_id']
    case.call('CompleteLesson', {'enrollment_id': bob['id'], 'lesson_id': lesson}, False)
    case.call('CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lesson})
    case.assert_private('LearningDashboard', 'courses', 'CompleteLesson', {'enrollment_id': alice['id'], 'lesson_id': lesson})
    result = case.finish('LearningDashboard')
    actual = next(row for row in result['expected_board']['enrollments'] if row['id'] == alice['id'])
    assert [row['sequence'] for row in actual['completed']] == [1, 2, 3, 4, 5]
    assert [row['lesson_id'] for row in actual['completed']] == [lessons[name]['id'] for name in ['Nodes', 'Edges', 'Traversal', 'Optimization']] + [lesson]
    assert len({row['lesson_id'] for row in actual['completed']}) == actual['total_lessons'] == 5
    assert next(row for row in result['expected_board']['enrollments'] if row['id'] == bob['id'])['completed'] == []
    return result


def library_loans(server, token, seed, directory):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    initial = case.call('LibraryCatalog', read=True)
    assert len(initial['libraries']) == 1 and len(initial['titles']) == 2 and len(initial['patrons']) == 4
    title = next(row for row in initial['titles'] if row['name'] == 'Graph Thinking')
    assert len(title['copies']) == 2 and title['edition'] == f'Edition {seed}'
    patrons = {row['name']: row['id'] for row in initial['patrons']}
    case.call('Seed', {'seed': seed})
    assert case.call('LibraryCatalog', read=True) == initial
    case.call('PlaceHold', {'title_id': title['id'], 'patron_id': patrons['Jordan']}, False)
    first = case.call('BorrowTitle', {'title_id': title['id'], 'patron_id': patrons['Avery']})['loan_id']
    case.call('BorrowTitle', {'title_id': title['id'], 'patron_id': patrons['Avery']}, False)
    second = case.call('BorrowTitle', {'title_id': title['id'], 'patron_id': patrons['Morgan']})['loan_id']
    case.call('BorrowTitle', {'title_id': title['id'], 'patron_id': patrons['Jordan']}, False)
    hold = case.call('PlaceHold', {'title_id': title['id'], 'patron_id': patrons['Jordan']})['hold_id']
    case.call('PlaceHold', {'title_id': title['id'], 'patron_id': patrons['Jordan']}, False)
    cancelled = case.call('PlaceHold', {'title_id': title['id'], 'patron_id': patrons['Casey']})['hold_id']
    case.call('CancelHold', {'hold_id': cancelled})
    case.call('CancelHold', {'hold_id': cancelled}, False)
    automatic = case.call('ReturnLoan', {'loan_id': first})['fulfilled_loan_id']
    assert automatic, 'Returning a copy must automatically lend it to the first queued patron'
    case.call('ReturnLoan', {'loan_id': first}, False)
    current = case.call('LibraryCatalog', read=True)
    filled = next(row for row in current['loans'] if row['id'] == automatic)
    assert filled['patron'] == 'Jordan' and filled['status'] == 'active'
    holds = next(row for row in current['titles'] if row['id'] == title['id'])['holds']
    assert [(row['position'], row['status']) for row in holds] == [(1, 'fulfilled'), (2, 'cancelled')]
    case.call('CancelHold', {'hold_id': hold}, False)
    case.call('ReturnLoan', {'loan_id': second})
    fourth = case.call('BorrowTitle', {'title_id': title['id'], 'patron_id': patrons['Casey']})['loan_id']
    case.assert_private('LibraryCatalog', 'libraries', 'ReturnLoan', {'loan_id': fourth})
    case.call('ReturnLoan', {'loan_id': automatic})
    case.call('ReturnLoan', {'loan_id': fourth})
    result = case.finish('LibraryCatalog')
    for book in result['expected_board']['titles']:
        for copy in book['copies']:
            active = [row for row in result['expected_board']['loans'] if row['copy_id'] == copy['id'] and row['status'] == 'active']
            assert len(active) <= 1 and copy['available'] == (not active)
    assert all(copy['available'] for book in result['expected_board']['titles'] for copy in book['copies'])
    return result


def event_seats(server, token, seed, directory):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    initial = case.call('EventCatalog', read=True)
    assert len(initial['venues']) == 1 and len(initial['events']) == 2
    event = next(row for row in initial['events'] if row['title'] == 'Graph Summit')
    workshop = next(row for row in initial['events'] if row['title'] == 'Data Workshop')
    seats = {row['label']: row for section in event['sections'] for row in section['seats']}
    other = workshop['sections'][0]['seats'][0]['id']
    assert set(seats) == {'A1', 'A2', 'A3'}
    case.call('Seed', {'seed': seed})
    assert case.call('EventCatalog', read=True) == initial
    a1, a2, a3 = [seats[key]['id'] for key in ('A1', 'A2', 'A3')]
    for invalid in [[], [a1, a1], [a1, other]]:
        case.call('HoldSeats', {'event_id': event['id'], 'seat_ids': invalid, 'reference': 'INVALID'}, False)
    assert case.call('EventCatalog', read=True) == initial
    held = case.call('HoldSeats', {'event_id': event['id'], 'seat_ids': [a1, a2], 'reference': 'CONFIRMED-ORDER'})['booking']
    expected_total = 2200 + seed % 3 * 200
    assert held['total_cents'] == expected_total and len(held['seat_ids']) == 2
    case.call('HoldSeats', {'event_id': event['id'], 'seat_ids': [a2], 'reference': 'OVERLAP'}, False)
    case.call('ConfirmBooking', {'booking_id': held['id']})
    case.call('ConfirmBooking', {'booking_id': held['id']}, False)
    cancelled = case.call('CancelBooking', {'booking_id': held['id']})['booking']
    assert cancelled['status'] == 'cancelled' and [row['amount_cents'] for row in cancelled['refunds']] == [expected_total]
    case.call('CancelBooking', {'booking_id': held['id']}, False)
    case.call('ConfirmBooking', {'booking_id': held['id']}, False)
    case.call('HoldSeats', {'event_id': event['id'], 'seat_ids': [a1], 'reference': 'CONFIRMED-ORDER'}, False)
    temporary = case.call('HoldSeats', {'event_id': event['id'], 'seat_ids': [a1], 'reference': 'TEMPORARY'})['booking']
    cancelled = case.call('CancelBooking', {'booking_id': temporary['id']})['booking']
    assert cancelled['refunds'] == []
    final_hold = case.call('HoldSeats', {'event_id': event['id'], 'seat_ids': [a3], 'reference': 'STILL-HELD'})['booking']
    case.assert_private('EventCatalog', 'venues', 'CancelBooking', {'booking_id': final_hold['id']})
    result = case.finish('EventCatalog')
    for event in result['expected_board']['events']:
        for section in event['sections']:
            for seat in section['seats']:
                active = [booking for booking in event['bookings'] if booking['status'] != 'cancelled' and seat['id'] in booking['seat_ids']]
                assert len(active) <= 1
                assert seat['status'] == ('available' if not active else 'held' if active[0]['status'] == 'held' else 'sold')
    return result


def help_queue(server, token, seed, directory):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    initial = case.call('DeskBoard', read=True)
    assert len(initial['desks']) == 1 and initial['desks'][0]['tick'] == 1000 + seed % 3
    assert len(initial['customers']) == len(initial['agents']) == 2 and len(initial['tickets']) == 1
    ticket = initial['tickets'][0]
    assert ticket['subject'] == 'Sensor offline' and ticket['response_minutes'] == 30
    riley = next(row['id'] for row in initial['agents'] if row['name'] == 'Riley')
    customer = initial['customers'][0]['id']
    case.call('Seed', {'seed': seed})
    assert case.call('DeskBoard', read=True) == initial
    case.call('ResolveTicket', {'ticket_id': ticket['id']}, False)
    case.call('AssignTicket', {'ticket_id': ticket['id'], 'agent_id': riley})
    case.call('AdvanceClock', {'minutes': -1}, False)
    case.call('AdvanceClock', {'minutes': 29})
    assert case.call('EvaluateSLA')['escalated_ids'] == []
    case.call('AdvanceClock', {'minutes': 1})
    assert case.call('EvaluateSLA')['escalated_ids'] == [ticket['id']]
    escalated = case.call('DeskBoard', read=True)['tickets'][0]
    assert escalated['escalated'] and [row['name'] for row in escalated['agents']] == ['Sam']
    case.call('AssignTicket', {'ticket_id': ticket['id'], 'agent_id': riley}, False)
    case.call('ReplyTicket', {'ticket_id': ticket['id'], 'body': 'Sensor replaced'})
    case.call('ResolveTicket', {'ticket_id': ticket['id']})
    case.call('ReplyTicket', {'ticket_id': ticket['id'], 'body': 'Late update'}, False)
    case.call('CreateTicket', {'subject': 'Invalid priority', 'customer_id': customer, 'priority': 'unknown'}, False)
    normal = case.call('CreateTicket', {'subject': 'Normal assistance', 'customer_id': customer, 'priority': 'normal'})['ticket']
    case.call('AdvanceClock', {'minutes': 31})
    case.call('EvaluateSLA')
    board = case.call('DeskBoard', read=True)
    assert not next(row for row in board['tickets'] if row['id'] == normal['id'])['escalated']
    case.call('ReplyTicket', {'ticket_id': normal['id'], 'body': 'Documentation provided'})
    case.call('ResolveTicket', {'ticket_id': normal['id']})
    late = case.call('CreateTicket', {'subject': 'Late first response', 'customer_id': customer, 'priority': 'urgent'})['ticket']
    case.call('AdvanceClock', {'minutes': 31})
    replied = case.call('ReplyTicket', {'ticket_id': late['id'], 'body': 'Escalated during reply'})['ticket']
    assert replied['escalated'] and [row['name'] for row in replied['agents']] == ['Sam']
    case.call('ResolveTicket', {'ticket_id': late['id']})
    case.assert_private('DeskBoard', 'desks', 'ResolveTicket', {'ticket_id': late['id']})
    result = case.finish('DeskBoard')
    for row in result['expected_board']['tickets']:
        assert row['status'] == 'resolved' and row['replies']
        late_response = row['replies'][0]['tick'] - row['opened_tick'] >= row['response_minutes']
        assert row['escalated'] is late_response
    return result
