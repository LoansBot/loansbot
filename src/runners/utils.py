"""Generally useful functions for runners"""
from datetime import datetime, timedelta
import time


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
