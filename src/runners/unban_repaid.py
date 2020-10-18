"""This runner is responsible for unbanning users when they've repaid all of
their loans.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
import perms.manager
import utils.reddit_proxy
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Count
from pypika.terms import Star
from functools import partial
from .utils import listen_event
import time

LOGGER_IDEN = 'runners/unban_repaid.py'
RPIDEN = 'unban_repaid'


def main():
    version = time.time()

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')
        # Close logger

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'loans.paid', partial(handle_loan_paid, version))


def handle_loan_paid(version, body):
    """Called when we detect a loan was repaid. If there are no more loans unpaid
    by the borrower, and the borrower is banned, we unban them.
    """
    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        borrower_username = body['borrower']['username']
        borrower_id = body['borrower']['id']
        was_unpaid = body['was_unpaid']

        itgs.logger.print(
            Level.TRACE,
            'Detected /u/{} repaid a loan',
            borrower_username
        )

        if not was_unpaid:
            itgs.logger.print(
                Level.TRACE,
                'Nothing to do about /u/{} repaying a loan - was not unpaid',
                borrower_username
            )
            return

        info = perms.manager.fetch_info(itgs, borrower_username, RPIDEN, version)
        if not info['borrow_banned']:
            itgs.logger.print(
                Level.TRACE,
                'Nothing to do about /u/{} repaying a loan - not banned',
                borrower_username
            )
            return

        loans = Table('loans')
        itgs.read_cursor.execute(
            Query.from_(loans)
            .select(Count(Star()))
            .where(loans.deleted_at.isnull())
            .where(loans.unpaid_at.notnull())
            .where(loans.borrower_id == Parameter('%s'))
            .get_sql(),
            (borrower_id,)
        )
        (cnt,) = itgs.read_cursor.fetchone()

        if cnt > 0:
            itgs.logger.print(
                Level.TRACE,
                'Nothing to do about /u/{} repaying a loan - still has {} unpaid loans',
                borrower_username, cnt
            )
            return

        itgs.logger.print(
            Level.DEBUG,
            'Unbanning /u/{} (no more loans unpaid)',
            borrower_username
        )
        utils.reddit_proxy.send_request(
            itgs, RPIDEN, version, 'unban_user',
            {
                'subreddit': 'borrow',
                'username': borrower_username
            }
        )
        perms.manager.flush_cache(itgs, borrower_username.lower())
        itgs.logger.print(
            Level.INFO,
            'Unbanned /u/{} - repaid all outstanding unpaid loans',
            borrower_username
        )
