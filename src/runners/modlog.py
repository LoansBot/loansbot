"""This is the entry point of a process which scans the borrow moderator queue
to speed up propagation of moderator events to our caches.

If a user is promoted to moderator, demoted from moderator, approved,
unapproved, banned, or unbanned we flush their permissions cache.
"""
import time
import os
import utils.reddit_proxy
import perms.manager
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lblogging import Level


MOST_RECENT_ACTION_SEEN_KEY = 'loansbot_runners_modlog_last_action_at'
PERMS_RELATED_ACTIONS = {
    'banuser': ('target_author',),
    'unbanuser': ('target_author',),
    'acceptmoderatorinvite': ('mod',),
    'removemoderator': ('target_author',),
    'addcontributor': ('target_author',),
    'removecontributor': ('target_author',)
}


def main():
    """Periodically scans the moderator log of /r/borrow to check if any users
    need their permissions cache flushed. This avoids permission checking
    scaling extremely poorly as there are more unique users"""
    version = time.time()
    with LazyItgs(logger_iden='runners/modlog.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up, version = {}', version)

    while True:
        with LazyItgs(logger_iden='runners/modlog.py#main') as itgs:
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
            if last_seen is None or act['created_at'] > last_seen:
                handle_action(itgs, act)
                new_last_seen = act['created_at']
            else:
                finished = True
                break

    if new_last_seen is not None:
        itgs.cache.set(MOST_RECENT_ACTION_SEEN_KEY, str(new_last_seen))


def handle_action(itgs, act):
    keys = PERMS_RELATED_ACTIONS.get(act['action'], tuple())
    for key in keys:
        username = act.get(key)
        if username is None:
            itgs.logger.print(
                Level.DEBUG,
                'Found modlog action {} by /u/{} - which we expected to ' +
                'have a key {} which would be the username for someone who ' +
                'should have their permissions rechecked, but it did not have one',
                act['action'], act['mod'], key
            )
        else:
            itgs.logger.print(
                Level.INFO,
                '/u/{} performed action {} toward /u/{}, so /u/{} will have ' +
                'their permissions rechecked on their next interaction, rather ' +
                'than relying on cached values.',
                act['mod'], act['action'], username, username
            )
            perms.manager.flush_cache(itgs, username)


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
