"""Diagnostic-only foreground callback profiles, never enabled for primary runs."""
import asyncio
import cProfile
import os
from pathlib import Path
import pstats
import threading
import time
from driver_probe import request_id

def install():
    original=asyncio.to_thread
    out=Path(os.environ['TTG_PERF_CPU_OUTPUT'])
    out.mkdir(parents=True,exist_ok=True)
    clock=os.environ.get('TTG_PERF_PROFILE_CLOCK','thread_cpu')
    if clock not in ('thread_cpu','wall'):
        raise ValueError('Diagnostic profile clock must be thread_cpu or wall')
    async def to_thread(func,*args,**kwargs):
        def profiled():
            rid=(request_id() or 'untracked').replace(':','-')
            profiler=cProfile.Profile(timer=time.thread_time) if clock=='thread_cpu' else cProfile.Profile()
            try:
                return profiler.runcall(func,*args,**kwargs)
            finally:
                name=f'{rid}-{threading.get_ident()}-{getattr(func,"__name__","callback")}-{clock}'
                profiler.dump_stats(str(out/(name+'.pstats')))
                with (out/(name+'.txt')).open('w') as file:
                    file.write('Foreground callback thread CPU; excludes other threads and blocking wait.\n' if clock=='thread_cpu'
                        else 'Foreground callback CALL/WALL profile; includes I/O and blocking time, not pure CPU.\n')
                    pstats.Stats(profiler,stream=file).strip_dirs().sort_stats('cumulative').print_stats(60)
        return await original(profiled)
    asyncio.to_thread=to_thread
