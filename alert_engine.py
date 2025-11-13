"""
This file has been moved to the package at `aischool/core/alert_engine.py`.
The root-level copy is retained as a small shim to avoid accidental imports.
Please import from `aischool.core.alert_engine` instead.
"""

from importlib import import_module

def _raise_moved():
    raise ImportError("alert_engine module moved to aischool.core.alert_engine; import from there")

__all__ = []

