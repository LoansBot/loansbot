"""This is the entry point of the comment-scanning daemon subprocess."""
import time
import os
import uuid
import json
from pypika import PostgreSQLQuery as Query, Table, Parameter
import traceback
import utils.reddit_proxy

from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
from lbshared.signal_helper import delay_signals


def main():
    """Connects to the database and AMQP service, then periodically scans for
    new comments in relevant subreddits."""
    summons = []
    version = time.time()

    with LazyIntegrations(logger_iden='runners/comments.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    while True:
        with LazyIntegrations(no_read_only=True, logger_iden='runners/comments.py#main') as itgs:
            scan_for_comments(itgs, version, summons)
        time.sleep(60)


def scan_for_comments(itgs, version, summons):
    """Scans for new comments using the given logger and amqp connection"""
    itgs.logger.print(Level.TRACE, 'Scanning for new comments..')
    after = None

    handled_fullnames = Table('handled_fullnames')

    while True:
        comments, after = _fetch_comments(itgs, version, after)

        if not comments:
            itgs.logger.print(Level.DEBUG, 'Found no more comments!')
            break

        fullnames = [comm['fullname'] for comm in comments]
        itgs.read_cursor.execute(
            Query.from_(handled_fullnames)
            .select('fullname')
            .where(handled_fullnames.fullname.isin([Parameter('%s') for f in fullnames]))
            .get_sql(),
            fullnames
        )
        rows = itgs.read_cursor.fetchall()

        itgs.logger.print(Level.TRACE, 'Found {} new comments', len(fullnames) - len(rows))

        if len(fullnames) == len(rows):
            break
        num_to_find = len(fullnames) - len(rows)
        seen_set = set(row[0] for row in rows)
        for comment in comments:
            if comment['fullname'] in seen_set:
                continue
            itgs.logger.print(Level.TRACE, 'Checking comment {}', comment['fullname'])

            summon_to_use = None
            for summon in summons:
                if not summon.might_apply_to_comment(comment):
                    continue
                summon_to_use = summon
                break

            num_to_find = num_to_find - 1
            with delay_signals(itgs):
                if summon_to_use is not None:
                    # TODO check author
                    itgs.logger.print(Level.DEBUG, 'Using summon {}', summon_to_use.name)
                    try:
                        summon_to_use.handle_comment(itgs, comment)
                    except:  # noqa
                        itgs.write_conn.rollback()
                        itgs.logger.exception(
                            Level.WARN,
                            'While using summon {} on comment {}',
                            summon_to_use.name, comment
                        )
                        traceback.print_exc()

                    itgs.write_conn.commit()

                itgs.write_cursor.execute(
                    Query.into(handled_fullnames)
                    .columns('fullname')
                    .insert(Parameter('%s'))
                    .get_sql(),
                    (comment['fullname'],)
                )
                itgs.write_conn.commit()

            itgs.logger.print(Level.TRACE, 'Finished handling comment {}', comment['fullname'])
            if num_to_find <= 0:
                break


def _fetch_comments(itgs, version, after=None):
    subreddits = os.environ['SUBREDDITS'].split(',')

    body = utils.reddit_proxy.send_request(
        itgs, 'comments', version, typ, {
            'subreddit': subreddits,
            'after': after
        }
    )

    if body['type'] != 'copy':
        itgs.logger.print(
            Level.INFO,
            'Got unexpected response type {} for comments request'
            '- treating as if there are no messages',
            body['type']
        )
        return [], None
    return body['info']['comments'], body['info'].get('after')
