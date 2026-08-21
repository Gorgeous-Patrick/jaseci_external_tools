"""Adapter factory for supported benchmark apps."""

from __future__ import annotations

from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.adapters.jacord import JacordAdapter
from lib.prefetch_exp.adapters.jdrive import JDriveAdapter
from lib.prefetch_exp.adapters.jsearch import JSearchAdapter
from lib.prefetch_exp.adapters.linked_list import LinkedListAdapter
from lib.prefetch_exp.adapters.littlex5 import LittleX5Adapter
from lib.prefetch_exp.models import SweepOptions


def make_adapter(options: SweepOptions) -> BenchmarkAdapter:
    adapters = {
        "jsearch": JSearchAdapter,
        "jdrive": JDriveAdapter,
        "jacord": JacordAdapter,
        "littlex5": LittleX5Adapter,
        "linked_list": LinkedListAdapter,
    }
    try:
        cls = adapters[options.manifest.name]
    except KeyError as exc:
        raise ValueError(f"no Python prefetch adapter for {options.manifest.name}") from exc
    return cls(options)
