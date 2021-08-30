"""Allows parsing the details part of a ban in the moderator log to determine
the unix duration of the ban
"""
import re


class TempBanDetailsParseError(Exception):
    pass


ALLOWED_DURATIONS = {
    'second': 1,
    'seconds': 1,
    'minute': 60,
    'minutes': 60,
    'hour': 3600,
    'hours': 3600,
    'day': 86400,
    'days': 86400,
    'week': 604800,
    'weeks': 604800
}
"""Allowed durations contains all the supported interval keywords as keys
and the values are the duration multiple.
"""

PARSE_REGEXES = [
    re.compile(r'Ban changed to (?P<cnt>\d+)\s+(?P<interval>\S+)', re.IGNORECASE),
    re.compile(r'(?P<cnt>\d+)\s+(?P<interval>\S+)')
]
"""The regexes to use for parsing temporary bans, in order of preference"""


def parse_temporary_ban(details: str) -> float:
    for regex in PARSE_REGEXES:
        grp = regex.match(details)
        if grp is not None:
            break
    else:
        raise TempBanDetailsParseError(
            f'invalid temporary ban details: {details} (does not match any regex)'
        )


    cnt = int(grp['cnt'])
    interval = grp['interval']

    if interval not in ALLOWED_DURATIONS:
        raise TempBanDetailsParseError(
            f'invalid temporary ban details: {details} (unknown interval: {interval})'
        )

    return cnt * ALLOWED_DURATIONS[interval]
