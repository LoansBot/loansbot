"""This is the entry point of the comment-scanning daemon subprocess."""
import time
import os
from pypika import PostgreSQLQuery as Query, Table, Parameter
import traceback
import utils.reddit_proxy
from summon_helper import handle_comment

from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations


def main():
    """Periodically scans for new comments in relevant subreddits."""
    version = time.time()

    with LazyIntegrations(logger_iden='runners/comments.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    while True:
        with LazyIntegrations(no_read_only=True, logger_iden='runners/comments.py#main') as itgs:
            try:
                scan_for_comments(itgs, version)
            except:  # noqa
                itgs.write_conn.rollback()
                itgs.logger.exception(
                    Level.ERROR,
                    'Unhandled exception while handling comments'
                )
                traceback.print_exc()
        time.sleep(60)


def scan_for_comments(itgs, version):
    """Scans for new comments using the given logger and amqp connection"""
    itgs.logger.print(Level.TRACE, 'Scanning for new comments..')
    after = None
    rpiden = 'comments'

    handled_fullnames = Table('handled_fullnames')

    itgs.logger.print(
        Level.TRACE,
        '[issue #59] Starting comment scan by fetching the first page of comments '
        'from newest to oldest.'
    )

    while True:
        comments, after = _fetch_comments(itgs, version, after)

        if not comments:
            itgs.logger.print(Level.DEBUG, 'Found no more comments!')
            break

        fullnames = [comm['fullname'] for comm in comments]

        itgs.logger.print(
            Level.TRACE,
            '[issue #59] Comments found: {}',
            ', '.join(fullnames)
        )

        itgs.read_cursor.execute(
            Query.from_(handled_fullnames)
            .select('fullname')
            .where(handled_fullnames.fullname.isin([Parameter('%s') for f in fullnames]))
            .get_sql(),
            fullnames
        )
        rows = itgs.read_cursor.fetchall()
        itgs.read_conn.commit()

        itgs.logger.print(Level.TRACE, 'Found {} new comments', len(fullnames) - len(rows))

        if len(fullnames) == len(rows):
            itgs.logger.print(
                Level.TRACE,
                '[issue #59] Since we have already seen all of these comments, we have '
                'definitely seen at least one comment from this page. By induction, '
                'we have also seen all older comments and can stop scanning.'
            )
            break

        num_to_find = len(fullnames) - len(rows)
        seen_set = set(row[0] for row in rows)

        itgs.logger.print(
            Level.TRACE,
            '[issue #59] New comments: {}',
            ', '.join(c for c in fullnames if c not in seen_set)
        )

        for comment in comments:
            if comment['fullname'] in seen_set:
                continue

            handle_comment(itgs, comment, rpiden, version)
            itgs.write_cursor.execute(
                Query.into(handled_fullnames)
                .columns('fullname')
                .insert(Parameter('%s'))
                .get_sql(),
                (comment['fullname'],)
            )
            itgs.write_conn.commit()

            num_to_find = num_to_find - 1
            if num_to_find <= 0:
                break

        if seen_set:
            itgs.logger.print(
                Level.TRACE,
                '[issue #59] In theory, since we have seen at least one comment '
                'from this page, we would expect to find no new comments on the '
                'next older page by induction. We will nonetheless fetch the next '
                'page (after={})',
                after
            )
        else:
            itgs.logger.print(
                Level.TRACE,
                '[issue #59] Since we have not seen any comments from this page, '
                'we need to fetch the next page (after={})',
                after
            )


def _fetch_comments(itgs, version, after=None):
    subreddits = os.environ['SUBREDDITS'].split(',')

    body = utils.reddit_proxy.send_request(
        itgs, 'comments', version, 'subreddit_comments', {
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
