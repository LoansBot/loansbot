"""Generally useful functions for runners"""
from datetime import datetime, timedelta
import time
import json
from lbshared.lazy_integrations import LazyIntegrations
from lblogging import Level


def sleep_until_hour_and_minute(hour, minute):
    """Sleep until the current clock time is HH:MM, where the hour is
    specified in 1-24 and minute in 0-59.
    """
    curtime = datetime.now()
    target_time = datetime(
        year=curtime.year,
        month=curtime.month,
        day=curtime.day,
        hour=hour,
        minute=minute
    )
    if curtime.hour > hour or curtime.hour == hour and curtime.minute >= minute:
        target_time += timedelta(days=1)
    time.sleep(target_time.timestamp() - time.time())


def listen_event(itgs, event_name, handler):
    """Listens for new events matching the given event name on the
    events topic exchange on rabbit mq. Whenever they come in this
    sends the through to the handler already decoded.
    """
    itgs.channel.exchange_declare(
        'events',
        'topic'
    )

    consumer_channel = itgs.amqp.channel()
    queue_declare_result = consumer_channel.queue_declare('', exclusive=True)
    queue_name = queue_declare_result.method.queue
    consumer_channel.queue_bind(queue_name, 'events', event_name)
    consumer = consumer_channel.consume(queue_name, inactivity_timeout=None)
    for method_frame, props, body_bytes in consumer:
        body_str = body_bytes.decode('utf-8')
        body = json.loads(body_str)

        try:
            handler(body)
        except:  # noqa
            itgs.logger.exception(Level.ERROR)
            consumer_channel.basic_nack(method_frame.delivery_tag, requeue=False)
            break

        consumer_channel.basic_ack(method_frame.delivery_tag)
    consumer_channel.cancel()


def listen_event_with_itgs(itgs, event_name, handler, keepalive=10):
    """Listen to events on the `"events"` topic exchange which match the given
    event name. When they come in, sends them to the `handler` function. Hence
    this operates very similarly to `listen_event`, except this also forwards
    a `LazyIntegrations` object to `handler`.

    It does _not_ forward the itgs object that it receives as an argument.
    Rather, it starts up a new `LazyIntegrations` if it does not have one open
    when receiving an event and forwards that integrations object to
    `handler`. This avoids keeping a database connection open while we are
    listening for events but not getting any, which would be wasteful.

    The integrations object that we open is reused until `keepalive` seconds pass
    without an event, and then we close it. This means that `handler` should be
    careful not to depend on implicit rollbacks; it should explicitly rollback.

    Arguments:
    - `itgs (LazyIntegrations)`: The lazy integrations to use for listening to
      the topic exchange. This should be fairly fresh as this function will not
      return naturally and hence any connections open in this `itgs` will stay
      alive even if they are not needed. Typically this is newly created.
      New `LazyIntegration` objects created by this function will copy `itgs`
      `logger_iden`.
    - `event_name (str)`: The name or pattern for events that should be listened
      for. May use a star (*) to substitute for exactly one word and a hash (#)
      to substitute for zero or more words.
    - `handler (callable)`: A function which we call with `(handler_itgs, event)`
      whenever we receive a matching event name. `handler_itgs` is an instance of
      `LazyIntegrations` and `event` is the payload of the event interpreted as
      utf-8 text and parsed as json.
    - `keepalive (int, float)`: If we do not receive an event for `keepalive`
      seconds after a previous event we will close the `LazyIntegrations` object
      we use for `handler` and will reopen it for the next event.

    Returns:
    - This function never returns unless an exception occurs, in which case the
      exception is logged and this function returns.
    """
    itgs.channel.exchange_declare(
        'events',
        'topic'
    )

    consumer_channel = itgs.amqp.channel()
    queue_declare_result = consumer_channel.queue_declare('', exclusive=True)
    queue_name = queue_declare_result.method.queue
    consumer_channel.queue_bind(queue_name, 'events', event_name)

    while True:
        consumer = consumer_channel.consume(queue_name, inactivity_timeout=None)
        handler_itgs = None
        for method_frame, props, body_bytes in consumer:
            break

        with LazyIntegrations(logger_iden=itgs.logger_iden) as handler_itgs:
            def handle_event():
                body_str = body_bytes.decode('utf-8')
                body = json.loads(body_str)

                try:
                    handler(handler_itgs, body)
                except:  # noqa
                    handler_itgs.logger.exception(Level.ERROR)
                    consumer_channel.basic_nack(method_frame.delivery_tag, requeue=False)
                    return False

                consumer_channel.basic_ack(method_frame.delivery_tag)
                return True

            cont = handle_event()
            consumer_channel.cancel()
            if not cont:
                break

            consumer = consumer_channel.consume(queue_name, inactivity_timeout=keepalive)
            for method_frame, props, body_bytes in consumer:
                if method_frame is None:
                    break
                cont = handle_event()
                if not cont:
                    break

            consumer_channel.cancel()
            if not cont:
                break
