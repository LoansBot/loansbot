"""This runner is responsible for occassionally fetching the current list of
moderators on the primary subreddits and diffing them with our internal list
of moderators then updating our list as necessary.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from pypika import PostgreSQLQuery as Query, Table, Parameter
import utils.reddit_proxy
import typing
import time
import os
import json

LOGGER_IDEN = 'runners/mod_sync.py'
LAST_CHECK_AT_KEY = 'runners/mod_sync/last_check_at'
TIME_BETWEEN_CHECKS_SECONDS = 60 * 60 * 24 * 7


def main():
    version = time.time()

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')
        last_check_at = _get_last_check_at(itgs)

    while True:
        the_time = time.time()
        if last_check_at is not None and (the_time - last_check_at) < TIME_BETWEEN_CHECKS_SECONDS:
            time.sleep(TIME_BETWEEN_CHECKS_SECONDS - the_time + last_check_at)
            continue

        with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
            sync_moderators_with_poll_and_diff(version, itgs)
            _set_last_check_at(itgs, the_time)
            last_check_at = the_time


def sync_moderators_with_poll_and_diff(version: float, itgs: LazyItgs) -> None:
    """Fetch the list of moderators from reddit, then diff them with who we
    know about, and then use that diff to update our list."""
    subreddits = os.environ['SUBREDDITS'].split(',')

    mods = set()
    for sub in subreddits:
        body = utils.reddit_proxy.send_request(
            itgs, 'mod_sync', version, 'subreddit_moderators', {
                'subreddit': sub
            }
        )

        if body['type'] != 'copy':
            itgs.logger.print(
                Level.INFO,
                'Got unexpected response type {} for subreddit moderators to {}'
                '- not syncing moderators',
                body['type'], sub
            )
            return

        for mod in body['info']['mods']:
            mods.add(mod['username'].lower())

    moderators = Table('moderators')
    users = Table('users')
    itgs.read_cursor.execute(
        Query.from_(moderators)
        .join(users).on(users.id == moderators.user_id)
        .select(users.username)
        .where(users.username.notin([Parameter('%s') for _ in mods]))
        .get_sql(),
        list(mods)
    )

    removed_mods = [r[0] for r in itgs.read_cursor.fetchall()]

    new_moderators = set(mods)
    itgs.read_cursor.execute(
        Query.from_(moderators)
        .join(users).on(users.id == moderators.user_id)
        .select(users.username)
        .where(users.username.isin([Parameter('%s') for _ in mods]))
        .get_sql(),
        list(mods)
    )
    row = itgs.read_cursor.fetchone()
    while row is not None:
        new_moderators.remove(row[0])
        row = itgs.read_cursor.fetchone()

    for removed_mod in removed_mods:
        itgs.logger.print(
            Level.INFO,
            'Detected that /u/{} is no longer a moderator',
            removed_mod
        )
        itgs.write_cursor.execute(
            'DELETE FROM moderators '
            'USING users '
            'WHERE users.id = moderators.user_id AND users.username=%s RETURNING users.id',
            (removed_mod,)
        )
        (removed_user_id,) = itgs.write_cursor.fetchone()
        itgs.write_conn.commit()
        itgs.channel.basic_publish(
            'events',
            'mods.removed',
            json.dumps({'username': removed_mod, 'user_id': removed_user_id})
        )

    for added_mod in new_moderators:
        itgs.logger.print(
            Level.INFO,
            'Detected that /u/{} is now a moderator',
            added_mod
        )
        itgs.write_cursor.execute(
            Query.into(moderators)
            .columns(moderators.user_id)
            .from_(users)
            .select(users.id)
            .where(users.username == Parameter('%s'))
            .returning(moderators.user_id)
            .get_sql(),
            (added_mod,)
        )
        (added_user_id,) = itgs.write_cursor.fetchone()
        itgs.write_conn.commit()
        itgs.channel.basic_publish(
            'events',
            'mods.added',
            json.dumps({'username': added_mod, 'user_id': added_user_id})
        )


def _get_last_check_at(itgs: LazyItgs) -> typing.Optional[float]:
    last_check_at_bytes: bytes = itgs.cache.get(LAST_CHECK_AT_KEY)
    if last_check_at_bytes is None:
        return None

    return float(last_check_at_bytes)


def _set_last_check_at(itgs: LazyItgs, new_last_check_at: float) -> None:
    itgs.cache.set(LAST_CHECK_AT_KEY, str(new_last_check_at))
