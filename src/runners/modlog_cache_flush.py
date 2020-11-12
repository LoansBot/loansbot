"""This is the entry point of a process which listens to the borrow moderator
queue to speed up propagation of privilege events to our caches.

If a user is promoted to moderator, demoted from moderator, approved,
unapproved, banned, or unbanned we flush their permissions cache.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from .utils import listen_event_with_itgs
import perms.manager

LOGGER_IDEN = 'runners/modlog_cache_flush.py'
PERMS_RELATED_ACTIONS = {
    'banuser': ('target_author',),
    'unbanuser': ('target_author',),
    'acceptmoderatorinvite': ('mod',),
    'removemoderator': ('target_author',),
    'addcontributor': ('target_author',),
    'removecontributor': ('target_author',)
}


def main():
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        listen_event_with_itgs(itgs, 'modlog.*', handle_action, keepalive=10)


def handle_action(itgs, act):
    if act['action'] not in PERMS_RELATED_ACTIONS:
        return

    keys = PERMS_RELATED_ACTIONS[act['action']]
    for key in keys:
        username = act.get(key)
        if username is None:
            itgs.logger.print(
                Level.DEBUG,
                'Found modlog action {} by /u/{} - which we expected to '
                + 'have a key {} which would be the username for someone who '
                + 'should have their permissions rechecked, but it did not have one',
                act['action'], act['mod'], key
            )
        else:
            itgs.logger.print(
                Level.INFO,
                '/u/{} performed action {} toward /u/{}, so /u/{} will have '
                + 'their permissions rechecked on their next interaction, rather '
                + 'than relying on cached values.',
                act['mod'], act['action'], username, username
            )
            perms.manager.flush_cache(itgs, username)
