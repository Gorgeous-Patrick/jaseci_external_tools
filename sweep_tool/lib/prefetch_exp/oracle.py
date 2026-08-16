"""Oracle UUID file generation."""

from __future__ import annotations

import csv
from pathlib import Path
from uuid import UUID


def oracle_file_path(
    oracle_dir: Path,
    app_name: str,
    walker: str,
    target_id: str,
    limit: int,
    trial: int,
) -> Path:
    safe_target = _safe_name(target_id or "default")
    return (
        oracle_dir
        / _safe_name(app_name)
        / _safe_name(walker)
        / f"{safe_target}_limit{limit}_trial{trial}.uuids"
    )


def write_oracle_from_access_log(access_log: Path, output_path: Path) -> list[str]:
    ids = extract_uuid_order(access_log)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(ids) + ("\n" if ids else ""))
    return ids


def extract_uuid_order(access_log: Path) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    if not access_log.exists():
        return out
    with open(access_log, newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "id" not in reader.fieldnames:
            return out
        for row in reader:
            if row.get("tier") == "MISS":
                continue
            raw = (row.get("id") or "").strip()
            if not raw:
                continue
            try:
                uid = str(UUID(raw))
            except ValueError:
                continue
            if uid in seen:
                continue
            seen.add(uid)
            out.append(uid)
    return out


def _safe_name(raw: str) -> str:
    keep = []
    for ch in str(raw):
        if ch.isalnum() or ch in ("-", "_", "."):
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep)[:160] or "default"
