"""Contains small utility functions which are useful through the program.
"""
import os
import psycopg2
import traceback
import time
import pika
from lblogging import Level
import signal
import atexit
from contextlib import contextmanager
from pymemcache.client import base as membase


def connect_to_database():
    """Connects to the database. Will retry up to 5 times with exponential
    backoff."""
    for attempt in range(5):
        if attempt > 0:
            sleep_time = 4 ** attempt
            print(f'Sleeping for {sleep_time} seconds..')
            time.sleep(sleep_time)

        print(f'Connecting to Postgres.. (attempt {attempt + 1}/5)')
        try:
            return psycopg2.connect('')
        except psycopg2.OperationalError:
            traceback.print_exc()

    raise Exception('Failed to connect to Postgres (and exhausted all attempts)')


def connect_to_amqp(logger):
    """Connects to the amqp server. Will retry up to 5 times with exponential
    backoff. Logs to the given logger (renamed)"""
    logger = logger.with_iden('helper.py')
    parameters = pika.ConnectionParameters(
        os.environ['AMQP_HOST'],
        int(os.environ['AMQP_PORT']),
        os.environ['AMQP_VHOST'],
        pika.PlainCredentials(
            os.environ['AMQP_USERNAME'], os.environ['AMQP_PASSWORD']
        )
    )

    for attempt in range(5):
        if attempt > 0:
            sleep_time = 4 ** attempt
            print(f'Sleeping for {sleep_time} seconds...')
            logger.print(Level.DEBUG, 'Sleeping for {} seconds...', sleep_time)
            logger.connection.commit()
            time.sleep(sleep_time)

        print(f'Connecting to AMQP.. (attempt {attempt + 1}/5)')
        logger.print(Level.TRACE, 'Connecting to AMQP (attempt {} of 5}', attempt + 1)
        logger.connection.commit()
        try:
            return pika.BlockingConnection(parameters)
        except pika.exceptions.AMQPConnectionError:
            traceback.print_exc()
            logger.exception(Level.WARN)
            logger.connection.commit()

    raise Exception('Failed to connect to AMQP (and exhausted all attempts)')


def connect_to_cache(logger):
    """Connects to the cache server. Will retry up to 5 times with exponential
    backoff. Logs to the given logger (renamed)"""
    logger = logger.with_iden('helper.py')
    host = os.environ['MEMCACHED_HOST']
    port = int(os.environ['MEMCACHED_PORT'])

    for attempt in range(5):
        if attempt > 0:
            sleep_time = 4 ** attempt
            print(f'Sleeping for {sleep_time} seconds...')
            logger.print(Level.DEBUG, 'Sleeping for {} seconds...', sleep_time)
            logger.connection.commit()
            time.sleep(sleep_time)

        print(f'Connecting to memcached.. (attempt {attempt + 1}/5)')
        logger.print(Level.TRACE, 'Connecting to memcached (attempt {} of 5}', attempt + 1)
        logger.connection.commit()
        try:
            client = membase.Client((host, port))
            client.get('test')
            return client
        except ConnectionRefusedError:
            traceback.print_exc()
            logger.exception(Level.WARN)
            logger.connection.commit()

    raise Exception('Failed to connect to memcached (and exhausted all attempts)')


def setup_clean_shutdown(logger, listeners):
    """This will listen for shutdown signals and invoke the given list of
    listeners exactly once. This will log using the given logger, but will
    not skip listeners solely due to logging issues"""
    logger = logger.with_iden('helper.py')

    shutdown_seen = False

    def handle_shutdown(sig_num=None, frame=None):
        nonlocal shutdown_seen
        if shutdown_seen:
            return
        shutdown_seen = True

        using_logger = True

        def _log(level, msg, *args):
            nonlocal using_logger
            if args:
                formatted = msg.format(*args)
            else:
                formatted = msg
            print(formatted)
            if using_logger:
                try:
                    logger.print(level, msg, *args)
                    logger.connection.commit()
                except:  # noqa
                    traceback.print_exc()
                    print('Not attempting to use the logger in setup_and_clean_shutdown anymore')
                    using_logger = False

        def _logexc(level):
            nonlocal using_logger
            traceback.print_exc()
            if using_logger:
                try:
                    logger.exception(level)
                    logger.connection.commit()
                except:  # noqa
                    traceback.print_exc()
                    print('Not attempting to use the logger in setup_and_clean_shutdown anymore')
                    using_logger = False

        if sig_num is not None:
            _log(Level.INFO, 'Clean shutdown started: Received signal {}', sig_num)
        else:
            _log(Level.INFO, 'Clean shutdown started (application exit)')

        for lst in listeners:
            try:
                lst()
            except:  # noqa
                _logexc(Level.WARN)

        _log(Level.INFO, 'Clean shutdown finished normally')
        logger.close()
        logger.connection.close()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    atexit.register(handle_shutdown)


@contextmanager
def signals_delayed(logger):
    """For the duration of the context manager, signals to terminate the
    program will be captured but not propagated. At the end of the context
    block, the signals will be repeated to the normal signal handlers.
    """
    logger = logger.with_iden('helper.py#signals_delayed')

    signals_detected = []

    def capture_signal(sig_num=None, frame=None):
        print(f'Capturing signal {sig_num} - signals are currently being delayed')
        logger.print(Level.INFO, 'Capturing signal {} - signals are currently being delayed', sig_num)
        signals_detected.append((sig_num, frame))

    old_sigint = signal.signal(signal.SIGINT, capture_signal)
    old_sigtrm = signal.signal(signal.SIGTERM, capture_signal)

    try:
        yield
    finally:
        for sig_num, frame in signals_detected:
            if sig_num == signal.SIGINT:
                old_sigint(sig_num, frame)
            elif sig_num == signal.SIGTERM:
                old_sigtrm(sig_num, frame)
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigtrm)
