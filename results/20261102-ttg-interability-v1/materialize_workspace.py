"""Materialize packaged non-archive source/evidence in a NEW review workspace."""
import argparse,json,hashlib,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();assert not out.exists();root=Path(__file__).resolve().parent
for r in json.loads((root/'manifests/path-mapping.json').read_text()):
 if 'archive_member' in r:continue
 rel=Path(r['original']);assert not rel.is_absolute() and '..' not in rel.parts
 src=root/r['package_path'];assert hashlib.sha256(src.read_bytes()).hexdigest()==r['sha256'];dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
print(out)
