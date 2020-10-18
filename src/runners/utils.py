"""Generally useful functions for runners"""
from datetime import datetime, timedelta
import time
import json


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
    consumer = consumer_channel.consume(queue_name, inactivity_timeout=600)
    for method_frame, props, body_bytes in consumer:
        if method_frame is None:
            continue
        body_str = body_bytes.decode('utf-8')
        body = json.loads(body_str)
        handler(body)
        consumer_channel.basic_ack(method_frame.delivery_tag)
    consumer.cancel()
