"""Same verified pre-seal gzip routine, restricted to new diagnostic evidence."""
import gzip
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'project-notes/measurements/ttg-performance-research-diagnostics-20261112'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def compress_closed_traces(directory,services_stopped):
    directory=Path(directory).resolve()
    if not services_stopped or not directory.is_relative_to(EVIDENCE):
        raise ValueError('Only stopped new diagnostic traces may be compressed')
    records=[]
    for path in sorted(directory.glob('server-*.jsonl')):
        if not path.name.endswith(('.calls.jsonl','.events.jsonl')):continue
        target=path.with_suffix(path.suffix+'.gz')
        if target.exists():raise ValueError('Duplicate raw/gzip trace')
        original=sha(path);size=path.stat().st_size
        with path.open('rb') as source,gzip.GzipFile(filename=str(target),mode='wb',mtime=0) as out:
            for block in iter(lambda:source.read(1024*1024),b''):out.write(block)
        check=hashlib.sha256()
        with gzip.open(target,'rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):check.update(block)
        if check.hexdigest()!=original:raise ValueError('Gzip decoded content mismatch')
        records.append(dict(raw_name=path.name,uncompressed_sha256=original,uncompressed_bytes=size,
                            sealed_name=target.name,gzip_sha256=sha(target),compressed_bytes=target.stat().st_size))
        path.unlink()
    return records
