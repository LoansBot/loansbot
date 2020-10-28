"""This is the entry point of a process which scans the borrow moderator queue
to speed up propagation of moderator events to our caches.

If a user is promoted to moderator, demoted from moderator, approved,
unapproved, banned, or unbanned we flush their permissions cache.
"""
import time
import os
import utils.reddit_proxy
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lblogging import Level
import json


LOGGER_IDEN = 'runners/modlog.py'
MOST_RECENT_ACTION_SEEN_KEY = 'loansbot_runners_modlog_last_action_at'
PRODUCER_ACTIONS = frozenset(
    'banuser', 'unbanuser',
    'acceptmoderatorinvite', 'removemoderator',
    'addcontributor', 'removecontributor'
)


def main():
    """Periodically scans the moderator log of /r/borrow to check if any users
    need their permissions cache flushed. This avoids permission checking
    scaling extremely poorly as there are more unique users"""
    version = time.time()
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up, version = {}', version)

    while True:
        with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
            itgs.channel.exchange_declare(
                'events',
                'topic'
            )

            scan_for_modactions(itgs, version)

        time.sleep(3600)


def scan_for_modactions(itgs: LazyItgs, version: float):
    itgs.logger.print(Level.TRACE, 'Scanning for new moderator actions..')
    after = None
    last_seen = itgs.cache.get(MOST_RECENT_ACTION_SEEN_KEY)
    if last_seen is not None:
        last_seen = float(last_seen)

    new_last_seen = last_seen
    finished = False
    while not finished:
        actions, after = _fetch_actions(itgs, version, after)
        if after is None:
            finished = True

        for act in actions:
            if last_seen is None or act['created_utc'] > last_seen:
                handle_action(itgs, act)
                new_last_seen = act['created_utc']
            else:
                finished = True
                break

    if new_last_seen is not None:
        itgs.cache.set(MOST_RECENT_ACTION_SEEN_KEY, str(new_last_seen))


def handle_action(itgs, act):
    if act['action'] not in PRODUCER_ACTIONS:
        return

    itgs.channel.basic_publish(
        'events',
        'modlog.' + act['action'],
        json.dumps(act)
    )


def _fetch_actions(itgs, version, after=None):
    subreddits = os.environ['SUBREDDITS'].split(',')

    body = utils.reddit_proxy.send_request(
        itgs, 'modlog', version, 'modlog', {
            'subreddits': subreddits,
            'after': after
        }
    )

    if body['type'] != 'copy':
        itgs.logger.print(
            Level.INFO,
            'Got unexpected response type {} for modlog request'
            '- treating as if there are no actions',
            body['type']
        )
        return [], None
    return body['info']['actions'], body['info'].get('after')
