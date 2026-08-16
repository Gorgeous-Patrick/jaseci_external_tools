"""Scoped TOML editing for Jac sweep config files."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class RunConfigEditor:
    """Patch keys in the top-level [run] section and restore on exit.

    The target benchmark configs keep the prefetch knobs in [run].  This
    helper intentionally edits only that section so app-specific config
    structure stays untouched.
    """

    def __init__(self, path: Path):
        self.path = path
        self._original = path.read_text()

    def restore(self) -> None:
        self.path.write_text(self._original)

    def patch(self, values: dict[str, Any]) -> None:
        text = self.path.read_text()
        lines = text.splitlines()
        start = self._find_section(lines, "run")
        if start is None:
            lines.extend(["", "[run]"])
            start = len(lines) - 1
        end = self._section_end(lines, start)

        existing: dict[str, int] = {}
        for idx in range(start + 1, end):
            stripped = lines[idx].strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            existing[key] = idx

        insert_at = end
        for key, value in values.items():
            rendered = f"{key} = {_toml_value(value)}"
            if key in existing:
                lines[existing[key]] = rendered
            else:
                lines.insert(insert_at, rendered)
                insert_at += 1

        self.path.write_text("\n".join(lines) + "\n")

    @staticmethod
    def _find_section(lines: list[str], name: str) -> int | None:
        needle = f"[{name}]"
        for idx, line in enumerate(lines):
            if line.strip() == needle:
                return idx
        return None

    @staticmethod
    def _section_end(lines: list[str], start: int) -> int:
        for idx in range(start + 1, len(lines)):
            stripped = lines[idx].strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                return idx
        return len(lines)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

