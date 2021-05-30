"""This is the entry point of a process which listens to the borrow moderator
queue to speed up propagation of privilege events to our caches.

If a user is promoted to moderator, demoted from moderator, approved,
unapproved, banned, or unbanned we flush their permissions cache.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from .utils import listen_event_with_itgs
from utils.account_utils import find_or_create_user
import perms.manager
import parsing.temp_ban_parser
from datetime import datetime
import time
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.terms import ExistsCriterion as Exists

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

            if act['action'] == 'banuser' and act['details'] != 'permanent':
                handle_temporary_ban(itgs, act)
            elif act['action'] in ('banuser', 'unbanuser'):
                clear_temporary_bans(itgs, username, act['subreddit'])


def handle_temporary_ban(itgs: LazyItgs, act: dict) -> None:
    username: str = act['target_author']
    mod_username: str = act['mod']
    details: str = act['details']
    subreddit = act['subreddit']

    try:
        ban_duration = parsing.temp_ban_parser.parse_temporary_ban(details)
    except parsing.temp_ban_parser.TempBanDetailsParseError:
        itgs.logger.exception(
            Level.WARN,
            'The temporary ban to {} has details {}: this could not be '
            + 'converted into a duration in seconds. This means we will '
            + 'not store the ban in temporary_bans, which means when the '
            + 'ban expires we will not flush their permission cache, which '
            + 'means it is possible the user will get stuck unable to interact '
            + 'with the loansbot. To workaround for this user, add/remove '
            + 'contributor once the ban expires.',
            username, repr(details)
        )
        return

    banned_user_id = find_or_create_user(itgs, username)
    mod_user_id = find_or_create_user(itgs, mod_username)

    temp_bans = Table('temporary_bans')
    itgs.write_cursor.execute(
        Query.into(temp_bans)
        .columns(
            temp_bans.user_id,
            temp_bans.mod_user_id,
            temp_bans.subreddit,
            temp_bans.ends_at
        )
        .insert(*(Parameter('%s') for _ in range(4)))
        .get_sql(),
        (banned_user_id, mod_user_id, subreddit, datetime.fromtimestamp(time.time() + ban_duration))
    )
    itgs.write_conn.commit()

    itgs.logger.print(
        Level.INFO,
        'Successfully processed a temporary ban on {} in {} by {} of {} ({} seconds)',
        username, subreddit, mod_username, details, ban_duration
    )


def clear_temporary_bans(itgs: LazyItgs, username: str, subreddit: str) -> None:
    temp_bans = Table('temporary_bans')
    users = Table('users')
    itgs.write_cursor.execute(
        Query.from_(temp_bans).delete()
        .where(Exists(
            Query.from_(users).select(1)
            .where(users.id == temp_bans.user_id)
            .where(users.username == Parameter('%s'))
        ))
        .where(temp_bans.subreddit == Parameter('%s'))
        .get_sql(),
        (username, subreddit)
    )
    itgs.write_conn.commit()

    itgs.logger.print(
        Level.DEBUG,
        'Deleted temporary bans for /u/{} on /r/{} (overriden by another '
        + 'mod action)',
        username, subreddit,
    )
