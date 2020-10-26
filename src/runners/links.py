"""This is the entry point for the link-scanning daemon process"""
import time
import os
import utils.reddit_proxy
import utils.req_post_interpreter
from lblogging import Level
import lbshared.user_settings as user_settings
from pypika import PostgreSQLQuery as Query, Table, Parameter
from perms import can_interact, IGNORED_USERS
from lbshared.lazy_integrations import LazyIntegrations
import traceback
import loan_format_helper
from lbshared.responses import get_response
import json

LOGGER_IDEN = 'runners/links.py'
"""The identifier for this runner in the logs"""


def main():
    """Periodically scans for new links in relevant subreddits."""
    version = time.time()

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    while True:
        with LazyIntegrations(no_read_only=True, logger_iden=LOGGER_IDEN) as itgs:
            try:
                scan_for_links(itgs, version)
            except:  # noqa
                itgs.write_conn.rollback()
                itgs.logger.exception(
                    Level.ERROR,
                    'Unhandled exception while handling links'
                )
                traceback.print_exc()
        time.sleep(120)


def scan_for_links(itgs, version):
    """Scans for new links"""
    itgs.logger.print(Level.TRACE, 'Scanning for new links..')
    after = None
    handled_fullnames = Table('handled_fullnames')

    while True:
        self_posts, url_posts, after = _fetch_links(itgs, version, after)

        if not self_posts and not url_posts:
            itgs.logger.print(Level.DEBUG, 'Found no more links!')
            break

        fullnames = [post['fullname'] for post in (self_posts + url_posts)]
        itgs.read_cursor.execute(
            Query.from_(handled_fullnames)
            .select('fullname')
            .where(handled_fullnames.fullname.isin([Parameter('%s') for f in fullnames]))
            .get_sql(),
            fullnames
        )
        rows = itgs.read_cursor.fetchall()
        itgs.read_conn.commit()

        itgs.logger.print(Level.TRACE, 'Found {} new links', len(fullnames) - len(rows))
        if len(fullnames) == len(rows):
            break
        num_to_find = len(fullnames) - len(rows)
        seen_set = set(row[0] for row in rows)

        for post in self_posts:
            if post['fullname'] in seen_set:
                continue
            _handle_self_post(itgs, version, post)
            itgs.write_cursor.execute(
                Query.into(handled_fullnames)
                .columns('fullname')
                .insert(Parameter('%s'))
                .get_sql(),
                (post['fullname'],)
            )
            itgs.write_conn.commit()
            num_to_find = num_to_find - 1
            if num_to_find <= 0:
                break

        if num_to_find > 0:
            for post in url_posts:
                if post['fullname'] in seen_set:
                    continue
                _handle_link_post(itgs, version, post)
                itgs.write_cursor.execute(
                    Query.into(handled_fullnames)
                    .columns('fullname')
                    .insert(Parameter('%s'))
                    .get_sql(),
                    (post['fullname'],)
                )
                itgs.write_conn.commit()
                num_to_find = num_to_find - 1
                if num_to_find <= 0:
                    break

        if after is None:
            break


def _handle_self_post(itgs, version, post):
    """Handles a post on a relevant subreddit which involves writing a markdown
    body. This assumes we have not already responded.

    Arguments:
        - itgs (LazyIntegrations): The integrations to use when connecting with
            networked components.
        - version (any): The version of this daemon that we're running, which
            we use to identify with the reddit proxy.
        - post (dict): The self-post that we are handling.
    """
    author = post['author']
    subreddit = post['subreddit']
    title = post['title']

    if not can_interact(itgs, author, 'links', version):
        if author.lower() not in IGNORED_USERS:
            itgs.logger.print(
                Level.INFO,
                'Using no summons for selfpost by /u/{} to /r/{}; insufficient access',
                author, subreddit
            )
        return

    if '[req]' not in title.lower():
        # This doesn't appear to be a request post. We allow users to opt out
        # of receiving a response to non-request posts.

        users = Table('users')
        itgs.read_cursor.execute(
            Query.from_(users)
            .select(users.id)
            .where(users.username == Parameter('%s'))
            .get_sql(),
            (author.lower(),)
        )
        row = itgs.read_cursor.fetchone()
        if row is not None:
            (user_id,) = row
            settings = user_settings.get_settings(itgs, user_id)

            if settings.non_req_response_opt_out:
                itgs.logger.print(
                    Level.DEBUG,
                    '/u/{} made a non-request post (title: {}); ignoring it because ' +
                    'they have opted out of receiving a check for non-request posts.',
                    author, title
                )
                return
    else:
        request = utils.req_post_interpreter.interpret(title)
        itgs.channel.exchange_declare(
            'events',
            'topic'
        )
        itgs.channel.basic_publish(
            'events',
            'loans.request',
            json.dumps({
                'post': post,
                'request': request.dict()
            })
        )

    itgs.logger.print(
        Level.INFO,
        '/u/{} made a post to /r/{}: "{}"; they are receiving a check.',
        author, subreddit, title
    )

    report = loan_format_helper.get_and_format_all_or_summary(itgs, author)
    formatted_response = get_response(
        itgs,
        'check',
        target_username=author,
        report=report
    )

    utils.reddit_proxy.send_request(
        itgs, 'links', version, 'post_comment',
        {
            'parent': post['fullname'],
            'text': formatted_response
        }
    )


def _handle_link_post(itgs, version, post):
    """Handles a post on a relevant subreddit which involves just linking to
    some other website."""
    itgs.logger.print(
        Level.INFO,
        'Ignoring a non-text submission from /u/{} on /r/{}: "{}"',
        post['author'], post['subreddit'], post['title']
    )


def _fetch_links(itgs, version, after=None):
    """Fetch all the links after the given cursor, plus the new cursor for
    fetching more (if there is more to fetch).

    Arguments:
        - itgs (LazyIntegrations): The lazy integrations to use to connect to
            networked components.
        - version (any): The unique version identifier for communicating with
            the reddir proxy.
        - after (str, None): The cursor value or None for starting with the most
            recent links.

    Returns:
        - self_links (list[dict]): The self-posts, otherwise known as text-posts.
        - url_links (list[dict]): The link-posts
        - after (str, None): The cursor for getting older posts or None if there
            are no older posts to get.

    See Also:
        reddit-proxy SubredditLinksHandler for the shape of the dicts.
    """
    subreddits = os.environ['SUBREDDITS'].split(',')

    body = utils.reddit_proxy.send_request(
        itgs, 'links', version, 'subreddit_links', {
            'subreddit': subreddits,
            'after': after
        }
    )

    if body['type'] != 'copy':
        itgs.logger.print(
            Level.INFO,
            'Got unexpected response type {} for links request'
            '- treating as if there are no messages',
            body['type']
        )
        return [], [], None
    return body['info']['self'], body['info']['url'], body['info'].get('after')
