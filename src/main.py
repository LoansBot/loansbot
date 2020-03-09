"""Main entry point into the application. This starts up each of the
subprocesses, which are capable of queueing jobs, then acts as a jobs worker.
This approach allows the loansbot to be parallelized on queries but
single-threaded for mutations.
"""
import helper
import os
from lblogging import Logger, Level
from multiprocessing import Process
import importlib
import time


SUBPROCESSES = ('runners.comments',)


def main():
    """Spawn all of the subprocesses as daemons and then works jobs until one
    one them dies or a signal to shutdown is received."""
    connection = helper.connect_to_database()
    logger = Logger(os.environ['APPNAME'], 'main.py', connection)
    logger.prepare()

    # We connect to the amqp service here to verify it's up
    amqp = helper.connect_to_amqp(logger)
    amqp.close()
    amqp = None

    # We connect to the cache service here to verify it's up
    memclient = helper.connect_to_cache(logger)
    memclient.close()
    memclient = None

    logger.print(Level.TRACE, 'Spawning subprocesses...')
    logger.connection.commit()
    subprocs = []
    for modnm in SUBPROCESSES:
        logger.print(Level.TRACE, 'Spawning subprocess {}', modnm)
        mod = importlib.import_module(modnm)
        proc = Process(target=mod.main, daemon=True)
        proc.start()
        subprocs.append(proc)
    logger.connection.commit()

    def shutdown_subprocs():
        logger.print(Level.INFO, 'Shutting down subprocesses... (pid={})', os.getpid())
        logger.connection.commit()
        for proc in subprocs:
            pid = proc.pid
            logger.print(Level.DEBUG, 'Shutting down pid={}', pid)
            logger.connection.commit()
            proc.terminate()
            proc.join()
            logger.print(Level.INFO, 'Shutdown subprocess pid={}', pid)
            logger.connection.commit()

    shutting_down = False

    def set_shutting_down():
        nonlocal shutting_down
        shutting_down = True

    helper.setup_clean_shutdown(logger, (shutdown_subprocs, set_shutting_down))

    print('Successfully started up')
    logger.print(Level.INFO, 'Successfully started up!')
    logger.connection.commit()

    while not shutting_down:
        running = True
        for proc in subprocs:
            if not proc.is_alive():
                logger.print(Level.ERROR, 'A child process has died! Terminating...')
                logger.connection.commit()
                running = False
                break
        if not running:
            break
        if shutting_down:
            break
        time.sleep(10)


if __name__ == '__main__':
    main()
