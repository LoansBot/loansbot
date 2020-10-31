"""This runner is responsible for listening to modlog events about gaining and
losing moderators and updating our set of moderators.
"""
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lblogging import Level
from pypika import PostgreSQLQuery as Query, Table, Parameter
from .utils import listen_event
import query_helper

LOGGER_IDEN = 'runners/mod_changes.py'
INTERESTING_ACTIONS = frozenset(('acceptmoderatorinvite', 'removemoderator'))


def main():
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'modlog.*', handle_action)


def handle_action(act):
    if act['action'] not in INTERESTING_ACTIONS:
        return

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        if act['action'] == 'acceptmoderatorinvite':
            new_mod_username = act['mod']
            user_id = _find_or_create_user(itgs, new_mod_username)
            if not _is_mod(itgs, user_id):
                _add_mod(itgs, user_id, commit=True)
                itgs.logger.print(
                    Level.INFO,
                    'Detected that /u/{} is now a moderator',
                    new_mod_username
                )
                itgs.channel.basic_publish(
                    'events',
                    'mods.added',
                    {'username': new_mod_username, 'user_id': user_id}
                )
        elif act['action'] == 'removemoderator':
            lost_mod_username = act['target_author']
            user_id = _find_or_create_user(itgs, new_mod_username)
            if _is_mod(itgs, user_id):
                _rem_mod(itgs, user_id, commit=True)
                itgs.logger.info(
                    Level.INFO,
                    'Detected that /u/{} is no longer a moderator',
                    lost_mod_username
                )
                itgs.channel.basic_publish(
                    'events',
                    'mods.removed',
                    {'username': lost_mod_username, 'user_id': user_id}
                )


def _find_or_create_user(itgs: LazyItgs, unm: str) -> int:
    users = Table('users')
    (user_id,) = query_helper.find_or_create_or_find(
        itgs,
        (
            Query.from_(users)
            .select(users.id)
            .where(users.username == Parameter('%s'))
            .get_sql(),
            (unm.lower(),)
        ),
        (
            Query.into(users)
            .columns(users.username)
            .insert(Parameter('%s'))
            .returning(users.id)
            .get_sql(),
            (unm.lower(),)
        )
    )
    return user_id


def _is_mod(itgs: LazyItgs, user_id: int) -> bool:
    moderators = Table('moderators')
    itgs.read_cursor.execute(
        Query.from_(moderators)
        .select(1)
        .where(moderators.user_id == Parameter('%s'))
        .get_sql(),
        (user_id,)
    )
    return itgs.read_cursor.fetchone() is not None


def _add_mod(itgs: LazyItgs, user_id: int, commit: bool = False):
    moderators = Table('moderators')
    itgs.write_cursor.execute(
        Query.into(moderators)
        .columns(moderators.user_id)
        .insert(Parameter('%s'))
        .get_sql(),
        (user_id,)
    )
    if commit:
        itgs.write_conn.commit()


def _rem_mod(itgs: LazyItgs, user_id: int, commit: bool = False):
    moderators = Table('moderators')
    itgs.write_cursor.execute(
        Query.from_(moderators)
        .delete()
        .where(moderators.user_id == Parameter('%s'))
        .get_sql(),
        (user_id,)
    )
    if commit:
        itgs.write_conn.commit()
