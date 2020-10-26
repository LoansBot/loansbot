"""This runner is responsible for scanning for borrowers which still have
active loans out making more requests. It sends a message to the lenders
for those borrowers, unless the lenders have opted out of receiving this
type of message."""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
import time
from pypika import Table, Parameter
import utils.reddit_proxy
import loan_format_helper
import json
from .utils import listen_event
from lbshared.responses import get_response
from lbshared.user_settings import get_settings
from functools import partial

LOGGER_IDEN = 'runners/borrower_request.py'
"""THe identity we use with the logger"""


def main():
    version = time.time()

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'loans.request', partial(handle_loan_request, version))


def handle_loan_request(version, event):
    """Handle a loan request event from the events queue.

    Arguments:
        version (any): The version to pass to the reddit proxy
        event (dict): Describes the request
            post (dict):
                A self post from reddit-proxy "subreddit_links" (Documented
                at reddit-proxy/src/handlers/links.py)
            request (dict):
                A dictified utils.req_post_interpreter.LoanRequest
    """
    post = event['post']
    with LazyIntegrations(logger_iden='runners/borrower_request.py#handle_loan_request') as itgs:
        itgs.logger.print(
            Level.TRACE,
            'Detected loan request from /u/{}',
            post['author']
        )

        users = Table('users')
        itgs.read_cursor.execute(
            users.select(users.id)
            .where(users.username == Parameter('%s'))
            .get_sql(),
            (post['author'].lower(),)
        )
        (author_user_id,) = itgs.read_cursor.fetchone()
        if author_user_id is None:
            itgs.logger.print(
                Level.TRACE,
                'Ignoring loan request from /u/{} - they do not have any ' +
                'outstanding loans (no history)',
                post['author']
            )
            return

        loans = Table('loans')
        itgs.read_cursor.execute(
            loan_format_helper.create_loans_query()
            .select(loans.lender_id)
            .where(loans.borrower_id == Parameter('%s'))
            .where(loans.repaid_at.isnull())
            .where(loans.unpaid_at.isnull())
            .get_sql(),
            (author_user_id,)
        )
        row = itgs.read_cursor.fetchone()
        outstanding_borrowed_loans = []
        while row is not None:
            outstanding_borrowed_loans.append({
                'pretty': loan_format_helper.fetch_loan(row[:-1]),
                'lender_id': row[-1]
            })
            row = itgs.read_cursor.fetchone()

        if not outstanding_borrowed_loans:
            itgs.logger.print(
                Level.TRACE,
                'Ignoring loan request from /u/{} - no outstanding loans',
                post['author']
            )
            return

        unique_lenders = frozenset(loan['lender_id'] for loan in outstanding_borrowed_loans)
        itgs.logger.print(
            Level.INFO,
            '/u/{} made a loan request while they have {} open loans from ' +
            '{} unique lenders: {}. Going to inform each lender which has not ' +
            'opted out of borrower request pms.',
            post['author'], len(outstanding_borrowed_loans), len(unique_lenders),
            unique_lenders
        )

        for lender_id in unique_lenders:
            lender_settings = get_settings(itgs, lender_id)
            if lender_settings.borrower_req_pm_opt_out:
                itgs.logger.print(
                    Level.TRACE,
                    'Not sending an alert to user {} - opted out',
                    lender_id
                )
                continue

            pretty_loans = [
                loan['pretty']
                for loan in outstanding_borrowed_loans
                if loan['lender_id'] == lender_id
            ]

            formatted_body = get_response(
                itgs,
                'borrower_request',
                lender_username=pretty_loans[0].lender,
                borrower_username=post['author'],
                thread='https://reddit.com/r/{}/comments/{}/redditloans'.format(
                    post['subreddit'], post['fullname'][3:]
                ),
                loans=loan_format_helper.format_loan_table(pretty_loans, include_id=True)
            )

            utils.reddit_proxy.send_request(
                itgs, 'borrower_request', version, 'compose',
                {
                    'recipient': post['author'],
                    'subject': '/u/{} has made a request thread'.format(post['author']),
                    'body': formatted_body
                }
            )
