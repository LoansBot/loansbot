"""This subprocess is responsibly for periodically polling the temporary_bans
table to see if any temporary bans have expired. If it finds one it flushes the
corresponding users permissions and deletes the row."""
import time
from pypika import PostgreSQLQuery as Query, Table, Parameter, Interval
from pypika.functions import Now
import traceback
from perms.manager import flush_cache

from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations


def main():
    """Periodically scans for expired temporary bans."""
    version = time.time()
    logger_iden = 'runners/temp_ban_expired_cache_flush.py#main'

    with LazyIntegrations(logger_iden=logger_iden) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    while True:
        with LazyIntegrations(no_read_only=True, logger_iden=logger_iden) as itgs:
            try:
                scan_for_expired_temp_bans(itgs, version)
            except:  # noqa
                itgs.write_conn.rollback()
                itgs.logger.exception(
                    Level.ERROR,
                    'Unhandled exception while handling expired temporary bans'
                )
                traceback.print_exc()
        time.sleep(600)


def scan_for_expired_temp_bans(itgs: LazyIntegrations, version: float) -> None:
    """Scans for any expired temporary bans in the temporary_bans table. For
    any rows that are found the corresponding users permission cache is flushed
    and the row is deleted."""

    temp_bans = Table('temporary_bans')
    users = Table('users')

    limit_per_iteration = 100
    # I don't anticipate there being that many temp bans that expire, so the
    # fact this races isn't that big of a concern. Furthermore, flushing the
    # cache on the same user twice in a row won't cause any issues. However,
    # I still implement the limit and looping to avoid OOM if for some reason
    # once in a blue moon a ton of temporary bans expire at once

    while True:
        itgs.write_cursor.execute(
            Query.from_(temp_bans)
            .select(
                temp_bans.id,
                users.username,
                temp_bans.subreddit,
                temp_bans.created_at,
                temp_bans.ends_at
            )
            .where(temp_bans.ends_at < Now() + Interval(minutes=1))
            .limit(limit_per_iteration)
            .get_sql()
        )

        rows = itgs.read_cursor.fetchall()

        for (rowid, username, subreddit, created_at, ends_at) in rows:
            itgs.logger.print(
                Level.INFO,
                'Detected a temporary ban on /u/{} in /r/{} at {} expired at {}; '
                + ' clearing users permission cache [rowid = {}]',
                username, subreddit, created_at, ends_at, rowid
            )
            flush_cache(itgs, username)

        itgs.write_cursor.execute(
            Query.from_(temp_bans).delete()
            .where(temp_bans.id.isin([Parameter('%s') for _ in rows]))
            .get_sql(),
            [row[0] for row in rows]
        )
        itgs.write_conn.commit()

        if len(rows) < limit_per_iteration:
            break
