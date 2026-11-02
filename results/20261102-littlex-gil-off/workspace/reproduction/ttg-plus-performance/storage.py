"""Verified pre-seal compression after natural owned service/worker completion."""
import gzip
import hashlib
from pathlib import Path
from interop import require,sha256
from plus_config import OWN,EVIDENCE


def compress_closed_traces(directory,services_stopped):
    require(services_stopped,'Trace compression requires stopped owned services')
    directory=Path(directory).resolve();records=[]
    require(directory.is_relative_to(OWN) or directory.is_relative_to(EVIDENCE),'Only NEW owned traces may be compressed')
    for path in sorted(directory.glob('server-*.jsonl')):
        if not path.name.endswith(('.calls.jsonl','.events.jsonl')):continue
        target=path.with_suffix(path.suffix+'.gz');require(not target.exists(),'Duplicate raw/gzip trace')
        original=sha256(path);size=path.stat().st_size
        with path.open('rb') as source,gzip.GzipFile(filename=str(target),mode='wb',mtime=0) as output:
            for chunk in iter(lambda:source.read(1024*1024),b''):output.write(chunk)
        digest=hashlib.sha256()
        with gzip.open(target,'rb') as source:
            for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
        require(digest.hexdigest()==original,'Compressed trace changed decoded bytes')
        records.append(dict(raw_name=path.name,uncompressed_sha256=original,uncompressed_bytes=size,
            sealed_name=target.name,gzip_sha256=sha256(target),compressed_bytes=target.stat().st_size))
        path.unlink()  # Owned, unsealed expansion only; verified gzip retained.
    return records
