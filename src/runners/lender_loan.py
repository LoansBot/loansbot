"""This runner is responsible for listening to new loans. Whenever someone
receives a loan who has already given out a loan we message r/borrow and
ensure they are removed from /r/lenderscamp
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
import time
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Count
from pypika.terms import Star
import utils.reddit_proxy
import perms.manager
import loan_format_helper
from lbshared.responses import get_response
from functools import partial
from .utils import listen_event

LOGGER_IDEN = 'runners/lender_loan.py'
RPIDEN = 'lender_loan'


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
        borrower_id = body['borrower']['id']
        itgs.logger.print(
            Level.TRACE,
            'Detected that /u/{} received a loan from /u/{}',
            borrower_username, lender_username
        )

        loans = Table('loans')
        itgs.read_cursor.execute(
            Query.from_(loans)
            .select(Count(Star()))
            .where(loans.deleted_at.isnull())
            .where(loans.lender_id == Parameter('%s'))
            .get_sql(),
            (borrower_id,)
        )
        (num_as_lender,) = itgs.read_cursor.fetchone()

        if num_as_lender == 0:
            itgs.logger.print(
                Level.TRACE,
                'Nothing to do - /u/{} has no loans as lender',
                borrower_username
            )
            return

        substitutions = {
            'lender_username': lender_username,
            'borrower_username': borrower_username,
            'loan_id': body['loan_id'],
            'loans_table': loan_format_helper.get_and_format_all_or_summary(itgs, borrower_username)
        }

        info = perms.manager.fetch_info(itgs, borrower_username, RPIDEN, version)
        if info['borrow_moderator']:
            itgs.logger.print(
                Level.DEBUG,
                'Ignoring that moderator /u/{} received a loan as lender',
                borrower_username
            )
            return

        if info['borrow_approved_submitter']:
            itgs.logger.print(
                Level.DEBUG,
                '/u/{} - who previously acted as lender - received a loan, '
                'but they are on the approved submitter list. Sending a pm but '
                'not taking any other action.',
                borrower_username
            )
            utils.reddit_proxy.send_request(
                itgs, RPIDEN, version, 'compose',
                {
                    'recipient': '/r/borrow',
                    'subject': get_response(
                        itgs, 'approved_lender_received_loan_modmail_pm_title', **substitutions),
                    'body': get_response(
                        itgs, 'approved_lender_received_loan_modmail_pm_body', **substitutions)
                }
            )
            return

        itgs.logger.print(
            Level.DEBUG,
            '/u/{} - who has previously acted as a lender - received a loan. '
            'Messaging moderators and ensuring they are not in /r/lenderscamp',
            borrower_username
        )

        utils.reddit_proxy.send_request(
            itgs, RPIDEN, version, 'compose',
            {
                'recipient': '/r/borrow',
                'subject': get_response(
                    itgs, 'lender_received_loan_modmail_pm_title', **substitutions),
                'body': get_response(
                    itgs, 'lender_received_loan_modmail_pm_body', **substitutions)
            }
        )

        is_approved = utils.reddit_proxy.send_request(
            itgs, RPIDEN, version, 'user_is_approved',
            {'subreddit': 'lenderscamp', 'username': borrower_username}
        )
        is_moderator = utils.reddit_proxy.send_request(
            itgs, RPIDEN, version, 'user_is_moderator',
            {'subreddit': 'lenderscamp', 'username': borrower_username}
        )
        if is_moderator:
            itgs.logger.print(
                Level.DEBUG,
                'Removing /u/{} as contributor on /r/lenderscamp suppressed - they are a mod there',
                borrower_username
            )
            return

        if is_approved:
            utils.reddit_proxy.send_request(
                itgs, RPIDEN, version, 'disapprove_user',
                {'subreddit': 'lenderscamp', 'username': borrower_username}
            )
            itgs.logger.print(
                Level.INFO,
                'Finished alerting about lender-gone-borrower /u/{} and removing from lenderscamp',
                borrower_username
            )
        else:
            itgs.logger.print(
                Level.INFO,
                'Alerted /r/borrow about /u/{} receiving a loan. They were '
                'already not a contributor to /r/lenderscamp.',
                borrower_username
            )
