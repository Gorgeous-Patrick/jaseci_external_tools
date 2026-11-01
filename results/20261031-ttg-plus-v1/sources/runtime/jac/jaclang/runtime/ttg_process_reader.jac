"""Independent Python/DB processes; parent threads only transfer raw rows."""
import json;
import os;
import subprocess;
import sys;
import from time { perf_counter }
import from threading { Lock }
import from uuid { UUID }
import from jaclang.data.store { AnchorRow, PgStore }

glob _CHILD = """
import contextlib, json, os, sys
with contextlib.redirect_stdout(sys.stderr):
    import jaclang
    from jaclang.data.store import ConnInfo, PgStore
from uuid import UUID
config = json.loads(sys.stdin.readline())
store = PgStore(conninfo=ConnInfo(**config['connection']),
                promotions=config['promotions'], auto_schema=False,
                pending_reset=False)
print(json.dumps({'ready': True, 'pid': os.getpid()}), flush=True)
try:
    for line in sys.stdin:
        request = json.loads(line)
        try:
            loaded = store.load_full([UUID(item) for item in request])
            rows = []
            for row in loaded.values():
                item = dict(vars(row))
                for key in ('id', 'root_id', 'src', 'dst'):
                    if item[key] is not None:
                        item[key] = str(item[key])
                if item['adjacency'] is not None:
                    item['adjacency'] = [str(uid) for uid in item['adjacency']]
                rows.append(item)
            result = {'pid': os.getpid(), 'rows': rows}
        except Exception as error:
            result = {'pid': os.getpid(), 'error': str(error)}
        print(json.dumps(result), flush=True)
finally:
    store.close()
""";

obj ProcessReader {
    has process: any,
        lock: any = None,
        startup_ms: float = 0.0;

    def init(store: any) {
        started = perf_counter();
        if not isinstance(store, PgStore) {
            raise TypeError('Process prefetch requires a PostgreSQL store');
        }
        self.lock = Lock();
        self.process = subprocess.Popen(
            [sys.executable, '-c', _CHILD],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1
        );
        config = {
            'connection': vars(store.conninfo),
            'promotions': dict(store.promotions)
        };
        self.process.stdin.write(json.dumps(config) + '\n');
        self.process.stdin.flush();
        ready = self.process.stdout.readline();
        expected = {'ready': True, 'pid': self.process.pid};
        if not ready or json.loads(ready) != expected {
            self.close();
            raise RuntimeError(
                'Prefetch reader process failed its readiness handshake'
            );
        }
        self.startup_ms = (perf_counter() - started) * 1000;
    }

    def load(ids: list) -> list[AnchorRow] {
        with self.lock {
            self.process.stdin.write(json.dumps([str(uid) for uid in ids]) + '\n');
            self.process.stdin.flush();
            line = self.process.stdout.readline();
            if not line {
                raise RuntimeError('Prefetch reader process exited before responding');
            }
            response = json.loads(line);
            if response['pid'] != self.process.pid or response['pid'] == os.getpid() {
                raise RuntimeError('Prefetch process identity mismatch');
            }
            if 'error' in response {
                raise RuntimeError(response['error']);
            }
            rows: list[AnchorRow] = [];
            for item in response['rows'] {
                for key in ['id', 'root_id', 'src', 'dst'] {
                    if item[key] is not None {
                        item[key] = UUID(item[key]);
                    }
                }
                if item['adjacency'] is not None {
                    item['adjacency'] = [UUID(uid) for uid in item['adjacency']];
                }
                rows.append(AnchorRow(**item));
            }
            return rows;
        }
    }

    def close {
        with self.lock {
            try {
                self.process.stdin.close();
                self.process.`wait(timeout=10);
            } except Exception {
                self.process.kill();
                self.process.`wait();
            } finally {
                self.process.stdout.close();
            }
        }
    }
}

def close_process_readers(mem: any) {
    for reader in getattr(mem, '_prefetch_process_readers', []) {
        reader.close();
    }
    setattr(mem, '_prefetch_process_readers', []);
}

def process_prefetch_worker(mem: any, ids: list, reader: ProcessReader, observer: any) {
    import from time { perf_counter }
    started = perf_counter();
    failure: str | None = None;
    try {
        with mem._raw_lock {
            cached = set(mem.__raw_mem__);
        }
        pending = [
            uid
            for uid in ids
            if uid not in mem.__mem__ and uid not in cached and uid not in mem._deleted
        ];
        if pending {
            for row in reader.load(pending) {
                mem.store_raw(row.id, row);
            }
        }
    } except Exception as error {
        failure = str(error);
    } finally {
        if observer is not None {
            observer(ids, (perf_counter() - started) * 1000, failure);
        }
    }
}
