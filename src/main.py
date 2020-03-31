"""Main entry point into the application. This starts up each of the
subprocesses, which are capable of queueing jobs, then acts as a jobs worker.
This approach allows the loansbot to be parallelized on queries but
single-threaded for mutations.
"""
from multiprocessing import Process
import importlib
import time
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
import lbshared.retry_helper as retry_helper
import atexit


SUBPROCESSES = ('runners.comments',)


def main():
    """Spawn all of the subprocesses as daemons and then works jobs until one
    one them dies or a signal to shutdown is received."""
    retry_helper.handle()

    subprocs = []
    with LazyIntegrations(logger_iden='main.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Booting up..')
        for modnm in SUBPROCESSES:
            itgs.logger.print(Level.TRACE, 'Spawning subprocess {}', modnm)
            mod = importlib.import_module(modnm)
            proc = Process(target=mod.main, daemon=True)
            proc.start()
            subprocs.append(proc)

    def onexit():
        try:
            with LazyIntegrations(logger_iden='main.py#main#onexit') as itgs:
                itgs.logger.print(Level.INFO, 'Shutting down')
        finally:
            for proc in subprocs:
                if proc.is_alive():
                    proc.terminate()

            for proc in subprocs:
                proc.join()

    atexit.register(onexit)

    running = True
    while running:
        time.sleep(10)
        for proc in subprocs:
            if not proc.is_alive():
                with LazyIntegrations(logger_iden='main.py#main') as itgs:
                    itgs.logger.print(Level.ERROR, 'A child process has died! Terminating...')
                running = False
                break


if __name__ == '__main__':
    main()
