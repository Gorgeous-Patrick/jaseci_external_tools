"""Accepted HTTP clock boundaries; uniform300s operation timeout."""
import json,time,urllib.request,urllib.error
from ia_interop import require

def post(self, path, body, token=None):
    rid = f'{self.generation}:{len(self.requests)}'
    headers = {'Content-Type': 'application/json', 'X-TTG-Perf-Request': rid}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    walker = path.split('/')[2] if path.startswith('/walker/') else None
    phase = 'setup' if not walker or walker in self._research_setup_walkers else self.phase
    if phase == 'workflow' and self.reset_next:
        headers['X-TTG-Perf-Reset-Profile'] = '1'
        self.reset_next = False
    request = urllib.request.Request(f'http://127.0.0.1:{self.port}' + path,
        data=json.dumps(body).encode(), headers=headers)
    wall_start = time.time()
    started = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw, status = response.read(), response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    ended = time.perf_counter_ns()
    wall_end = time.time()
    result = json.loads(raw)
    # This channel executes only AFTER application HTTP completion and is
    # excluded from http_e2e_ms. It also serializes deferred trace metadata.
    control = urllib.request.Request(f'http://127.0.0.1:{self.control_port}/drain', data=b'',
        headers={'X-TTG-Perf-Drain-Request': rid})
    with urllib.request.urlopen(control, timeout=40) as response:
        drained = json.loads(response.read())
    require(drained['pending'] == 0, f'Late prefetch drain failed: {rid}')
    record = dict(request=rid, phase=phase, path=path, input=body if walker else '<setup credentials omitted>',
        output=result if walker else '<setup authentication omitted>', http_status=status,
        http_e2e_ms=(ended-started)/1e6, start_ns=started, end_ns=ended,
        wall_start=wall_start, wall_end=wall_end, post_response_drain=drained,
        server_generation=self.generation)
    self.requests.append(record)
    with (self.directory / 'http-raw.jsonl').open('a') as file:
        file.write(json.dumps(record) + '\n')
    require(200 <= status < 300 and result.get('ok') is not False and not result.get('error'), f'{path}: {status}: {result}')
    data = result.get('data', result)
    if walker and self.phase == 'workflow':
        self.transcript.append(dict(walker=walker, target=path.split('/')[3:] or [], input=body, output=data))
    if walker in ('Seed', 'SuiteImport') and self.fixture is None and self.capture_fixture:
        self.fixture = self.capture_fixture()
    return data
