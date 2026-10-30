"""Separate diagnostic entrypoint; primary/clean entrypoint remains unchanged."""
import cpu_profile
cpu_profile.install()
import atexit
from driver_probe import flush
atexit.register(flush)
import perf_serve
