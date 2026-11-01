#!/usr/bin/env python3
"""Stream an exact decoded member from a verified portable case archive."""
import argparse
import sys
import tarfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--member');args=p.parse_args()
with tarfile.open(args.archive,'r|xz') as archive:
    for member in archive:
        if args.member is None:print(member.name)
        elif member.name==args.member:
            with archive.extractfile(member) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):sys.stdout.buffer.write(block)
            break
    else:
        if args.member is not None:raise SystemExit('Member not found')
