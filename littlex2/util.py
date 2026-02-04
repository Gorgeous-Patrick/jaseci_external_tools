import json
from pathlib import Path
from typing import Any


def append_to_json_list(path: str | Path, item: Any) -> None:  # noqa: ANN401
    path = Path(path)

    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    if not isinstance(data, list):
        raise ValueError(f"JSON in {path} is not a list")

    data.append(item)

    # write back atomically-ish
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp_path.replace(path)
