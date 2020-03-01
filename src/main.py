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

    helper.setup_clean_shutdown(logger, [])

    # We connect to the amqp service here to verify it's up
    amqp = helper.connect_to_amqp(logger)
    amqp.close()
    amqp = None

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

    print('Successfully started up')
    logger.print(Level.INFO, 'Successfully started up!')
    logger.connection.commit()

    while True:
        running = True
        for proc in subprocs:
            if not proc.is_alive():
                logger.print(Level.ERROR, 'A child process has died! Terminating...')
                logger.connection.commit()
                running = False
                break
        if not running:
            break
        time.sleep(10)


if __name__ == '__main__':
    main()
