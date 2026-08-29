"""Manifest loader.

A manifest is a YAML file describing one benchmarkable app: where it
lives, which sweep script drives it, what env-var-backed parameters
the frontend should expose, and where the outputs land.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_APP_ORDER = ("linked_list", "jacord", "littlex5", "jdrive")


@dataclass
class Parameter:
    name: str
    label: str
    kind: str  # "int" | "int_list" | "enum" | "str"
    default: Any
    help: str = ""
    choices: list[Any] = field(default_factory=list)


@dataclass
class Manifest:
    name: str
    description: str
    app_dir: Path                    # absolute
    runner: str                      # "shell" | "prefetch_python"
    sweep_script: str                # relative to app_dir
    results_csv: str                 # relative to app_dir
    logs_dir: str                    # relative to app_dir
    profiles_dir: str                # relative to app_dir
    parameters: list[Parameter]
    manifest_path: Path

    def env_from_form(self, values: dict[str, Any]) -> dict[str, str]:
        """Convert a form-submission dict to the env vars the sweep
        script expects.  int_list -> space-joined string; everything
        else -> str()."""
        env: dict[str, str] = {}
        for p in self.parameters:
            v = values.get(p.name, p.default)
            if p.kind == "int_list":
                env[p.name] = " ".join(str(x) for x in v)
            else:
                env[p.name] = str(v)
        return env


def load(path: Path) -> Manifest:
    data = yaml.safe_load(path.read_text())
    scripts = data.get("scripts", {})
    outputs = data.get("outputs", {})
    params_raw = data.get("parameters", [])

    app_dir = (path.parent / data["app_dir"]).resolve()
    params = [
        Parameter(
            name=p["name"],
            label=p.get("label", p["name"]),
            kind=p.get("kind", "str"),
            default=p.get("default"),
            help=p.get("help", ""),
            choices=p.get("choices", []),
        )
        for p in params_raw
    ]
    return Manifest(
        name=data["name"],
        description=data.get("description", ""),
        app_dir=app_dir,
        runner=data.get("runner", "shell"),
        sweep_script=scripts.get("sweep", "sweep.sh"),
        results_csv=outputs.get("results_csv", "results.csv"),
        logs_dir=outputs.get("logs_dir", "logs"),
        profiles_dir=outputs.get("profiles_dir", "profiles"),
        parameters=params,
        manifest_path=path,
    )


def discover(manifest_dir: Path) -> list[Manifest]:
    order = {name: i for i, name in enumerate(DEFAULT_APP_ORDER)}
    return sorted(
        (load(p) for p in manifest_dir.glob("*.yaml")),
        key=lambda m: (order.get(m.name, len(order)), m.name),
    )
