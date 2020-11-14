"""This runner is responsible for listening for new loans and flairing the
thread completed when it sees them.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
import utils.reddit_proxy
from .utils import listen_event
from functools import partial
import time


LOGGER_IDEN = 'runners/flair_loan_threads_completed.py'
"""The identifier we use when logging"""

RPIDEN = 'flair_loan_threads_completed'
"""The identifier we use to communicate to the reddit proxy"""

CSS_CLASS = '991c8042-3ecc-11e4-8052-12313d05258a'
"""The flair CSS class that we apply"""


def main():
    version = time.time()

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'loans.create', partial(handle_loan_created, version))


def handle_loan_created(version, body):
    """Called whenever we detect that a loan was just created.

    Arguments:
    - `version (float)`: The version for communicating with the reddit-proxy
    - `body (dict)`: The body of the loans.create event
    """
    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        lender_username = body['lender']['username']
        borrower_username = body['borrower']['username']
        link_fullname = body['comment']['link_fullname']
        subreddit = body['comment']['subreddit']
        permalink = body['permalink']

        itgs.logger.print(
            Level.DEBUG,
            'Detected that /u/{} lent some money to /u/{} in link {} (in /r/{})',
            lender_username, borrower_username, link_fullname, subreddit
        )

        utils.reddit_proxy.send_request(
            itgs, RPIDEN, version, 'flair_link',
            {'subreddit': subreddit, 'link_fullname': link_fullname, 'css_class': CSS_CLASS}
        )

        itgs.logger.print(
            Level.INFO,
            'Flaired {} as completed',
            permalink
        )
