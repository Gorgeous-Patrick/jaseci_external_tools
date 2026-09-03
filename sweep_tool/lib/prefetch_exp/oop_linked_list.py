"""Compatibility wrapper for LinkedList's in-app OOP/CAPRe implementation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


APP_MODULE_PATH = Path(__file__).resolve().parents[3] / "linked_list" / "oop_capre.py"
SPEC = importlib.util.spec_from_file_location("_linked_list_oop_capre", APP_MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"cannot load LinkedList OOP/CAPRe module from {APP_MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

for NAME in MODULE.__all__:
    globals()[NAME] = getattr(MODULE, NAME)

__all__ = list(MODULE.__all__)
