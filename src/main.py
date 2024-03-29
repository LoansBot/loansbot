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
import signal


SUBPROCESSES = (
    'runners.comments', 'runners.rechecks', 'runners.links',
    'runners.new_lender', 'runners.borrower_request', 'runners.default_permissions',
    'runners.trust_loan_delays', 'runners.deprecated_alerts', 'runners.loans_stats',
    'runners.ban_unpaid', 'runners.lender_loan', 'runners.recheck_permission',
    'runners.lender_queue_trusts', 'runners.modlog', 'runners.modlog_cache_flush',
    'runners.mod_changes', 'runners.mod_offboarding', 'runners.mod_onboarding_claim',
    'runners.mod_onboarding', 'runners.mod_sync', 'runners.mod_onboarding_messages',
    'runners.flair_loan_threads_completed', 'runners.temp_ban_expired_cache_flush',
)


def subprocess_runner(name):
    """Runs the given submodule

    Arguments:
    - `name (str)`: The name of the module to run
    """
    mod = importlib.import_module(name)

    try:
        mod.main()
    except:  # noqa
        with LazyIntegrations(logger_iden='main.py#subprocess_runner') as itgs:
            itgs.logger.exception(
                Level.WARN,
                'Child process {} failed with an unhandled exception',
                name
            )


def main():
    """Spawn all of the subprocesses as daemons and then works jobs until one
    one them dies or a signal to shutdown is received."""
    retry_helper.handle()

    subprocs = []
    with LazyIntegrations(logger_iden='main.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Booting up..')
        for modnm in SUBPROCESSES:
            itgs.logger.print(Level.TRACE, 'Spawning subprocess {}', modnm)
            proc = Process(target=subprocess_runner, name=modnm, args=(modnm,), daemon=True)
            proc.start()
            subprocs.append(proc)

    shutting_down = False

    def onexit(*args, **kwargs):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
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
    signal.signal(signal.SIGINT, onexit)
    signal.signal(signal.SIGTERM, onexit)

    running = True
    while running and not shutting_down:
        for proc in subprocs:
            if not proc.is_alive():
                with LazyIntegrations(logger_iden='main.py#main') as itgs:
                    itgs.logger.print(Level.ERROR, 'A child process has died ({})! Terminating...', proc.name)
                running = False
                break
        if not running:
            break
        for _ in range(20):
            time.sleep(0.5)
            if shutting_down:
                break


if __name__ == '__main__':
    main()
