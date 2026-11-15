"""Browser orchestration and independent native checks of browser-created state."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def verify_browser(app, backend, directory):
    from native import free_port, SUITE, write_json
    port = free_port()
    config = directory / 'ui-config.json'
    write_json(config, {})
    with (directory / 'frontend.log').open('w') as log:
        process = subprocess.Popen([sys.executable, str(SUITE / 'ui_server.py'), '--app', app,
                                    '--backend', f'http://127.0.0.1:{backend.port}', '--config', str(config),
                                    '--port', str(port)], stdout=log, stderr=subprocess.STDOUT)
        try:
            url = f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url, timeout=1):
                        break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError('Frontend server exited')
                    time.sleep(0.1)
            environment = {**os.environ, 'PLAYWRIGHT_BROWSERS_PATH': os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/tmp/ttg-suite-browsers')}
            result = subprocess.run(['node', str(SUITE / 'browser.mjs'), app, url, str(directory)],
                                    env=environment, capture_output=True, text=True)
            (directory / 'browser.log').write_text(result.stdout + result.stderr)
            result.check_returncode()
            return json.loads((directory / 'browser-result.json').read_text())
        finally:
            process.terminate()
            process.wait(timeout=10)


def verify_browser_persistence(app, server, token, result):
    events = result['events']
    if app == 'littlex':
        post = next(event for event in events if event['action'] == 'create_tweet')
        rows = server.walker('load_feed', {}, token)[0]
        actual = next(row for row in rows if row['id'] == post['id'])
        assert actual['content'] == post['content'] and 'user_0000' in actual['likes']
    elif app == 'jacord':
        reply = next(event for event in events if event['action'] == 'post_reply')
        rows = server.walker('load_channel', {}, token, reply['channel'])
        actual = next(row for row in rows if row['id'] == reply['id'])
        assert actual['content'] == reply['content'] and actual['author_username'] == 'user_0000'
    elif app == 'jdrive':
        folder = next(event for event in events if event['action'] == 'mkdir')
        rows = server.walker('ListFolder', {}, token, folder['parent'])[0]['entries']
        assert any(row['id'] == folder['id'] and row['name'] == folder['name'] for row in rows)
        trashed = next(event for event in events if event['action'] == 'trash')
        assert not any(row['id'] == trashed['id'] for row in rows)
    elif app == 'issue_desk':
        board = server.walker('ProjectBoard', {}, token)[0]
        actual = next(row for row in board['issues'] if row['title'] == 'Browser release checklist')
        assert actual['status'] == 'closed'
        assert [row['name'] for row in actual['assignees']] == ['Morgan']
        assert [row['body'] for row in actual['comments']] == ['Reviewed in browser']
        assert [row['title'] for row in actual['blockers']] == ['Implement parser fix']
    elif app == 'approval_desk':
        expenses = server.walker('ExpenseBoard', {}, token)[0]['expenses']
        actual = next(row for row in expenses if row['title'] == 'Browser equipment order')
        assert actual['status'] == 'paid' and actual['total_cents'] == 60000
        assert [row['decision'] for row in actual['steps']] == ['approved', 'approved']
        assert len(actual['payments']) == 1 and actual['payments'][0]['amount_cents'] == 60000
    elif app == 'stock_room':
        inventory = server.walker('Inventory', {}, token)[0]
        actual = next(row for row in inventory['reservations'] if row['reference'] == 'BROWSER-ORDER')
        assert actual['status'] == 'dispatched' and actual['quantity'] == 3
        assert sum(row['quantity'] for row in actual['allocations']) == 3
        assert len([row for row in inventory['dispatches'] if row['reservation_id'] == actual['id']]) == 1
        for lot in inventory['lots']:
            active = sum(allocation['quantity'] for reservation in inventory['reservations']
                         if reservation['status'] == 'reserved' for allocation in reservation['allocations']
                         if allocation['lot_id'] == lot['id'])
            assert lot['received'] == lot['available'] + lot['dispatched'] + active
    elif app == 'clinic_queue':
        schedule = server.walker('ClinicSchedule', {}, token)[0]
        appointments = [item for slot in schedule['slots'] for item in slot['appointments']]
        assert len([item for item in appointments if item['patient'] == 'Browser Patient' and item['status'] == 'cancelled']) == 1
        assert len([item for item in appointments if item['patient'] == 'Browser Rebook' and item['status'] == 'booked']) == 1
    elif app == 'course_path':
        dashboard = server.walker('LearningDashboard', {}, token)[0]
        learner = next(row for row in dashboard['enrollments'] if row['learner'] == 'Browser Learner')
        assert len(learner['completed']) == learner['total_lessons'] == 5
        assert [row['sequence'] for row in learner['completed']] == [1, 2, 3, 4, 5]
    elif app == 'library_loans':
        catalog = server.walker('LibraryCatalog', {}, token)[0]
        title = next(row for row in catalog['titles'] if row['name'] == 'Graph Thinking')
        active = [row for row in catalog['loans'] if row['title_id'] == title['id'] and row['status'] == 'active']
        assert sorted(row['patron'] for row in active) == ['Jordan', 'Morgan']
        assert len({row['copy_id'] for row in active}) == 2
        assert all(not row['available'] for row in title['copies'])
        assert not any(row['status'] == 'queued' for row in title['holds'])
    elif app == 'event_seats':
        catalog = server.walker('EventCatalog', {}, token)[0]
        event = next(row for row in catalog['events'] if row['title'] == 'Graph Summit')
        booking = next(row for row in event['bookings'] if row['reference'] == 'BROWSER-BOOKING')
        assert booking['status'] == 'cancelled' and len(booking['seat_ids']) == 2
        assert [row['amount_cents'] for row in booking['refunds']] == [booking['total_cents']]
        seats = [row for section in event['sections'] for row in section['seats']]
        assert all(row['status'] == 'available' for row in seats if row['id'] in booking['seat_ids'])
    elif app == 'help_queue':
        board = server.walker('DeskBoard', {}, token)[0]
        ticket = next(row for row in board['tickets'] if row['subject'] == 'Browser escalation')
        assert ticket['status'] == 'resolved' and ticket['escalated']
        assert [row['name'] for row in ticket['agents']] == ['Sam']
        assert [row['body'] for row in ticket['replies']] == ['Replaced the test sensor']
    else:
        from additional_scenarios import verify_browser as verify_additional
        verify_additional(app, server, token)
