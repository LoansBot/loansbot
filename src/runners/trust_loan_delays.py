"""Manages trust loan delays triggering. A trust loan delay is when a moderator
requests that a user be re-added to the trust queue after they reach a certain
number of loans completed as lender.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
from lbshared.money import Money
import lbshared.delayed_queue as delqueue
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Count, Star
from datetime import datetime
import time
from functools import partial
from .utils import listen_event


def main():
    version = time.time()

    with LazyIntegrations(logger_iden='runners/trust_loan_delays.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyIntegrations(logger_iden='runners/trust_loan_delays.py#main') as itgs:
        # Keeps as few connections alive as possible when not working
        listen_event(itgs, 'loans.paid', partial(handle_loan_paid, version))


def handle_loan_paid(version, body):
    """Called when we detect that a loan was repaid. Checks for any loan
    delays and, if there are any, checks if they are triggered. If they
    are triggered this removes the loan delay and adds the lender to the
    trust queue.

    Arguments:
    - `version (float)`: Our version string when using the reddit proxy.
    - `body (dict)`: The event body. Has the following keys:
      - `loan_id (int)`: The id of the loan which was just repaid
      - `lender (dict)`: The lender for the loan. Has the following keys:
        - `id (int)`: The id of the user who lent the money
        - `username (str)`: The username of the user who lent the money
      - `borrower (dict)`: The borrower for the loan. Has the following keys:
        - `id (int)`: The id of the user who borrowed the money
        - `username (str)`: The username of the user who borrowed the money
      - `amount (dict)`: The total principal of the loan which is now repaid.
        Essentially a serialized Money object.
      - `was_unpaid (bool)`: True if the loan was unpaid, false if it was not.
    """
    with LazyIntegrations(
            logger_iden='runners/trust_loan_delays.py#handle_loan_paid',
            no_read_only=True) as itgs:
        money = Money(**body['amount'])
        itgs.logger.print(
            Level.TRACE,
            'Detected a {} loan from /u/{} to /u/{} was repaid',
            money, body['lender']['username'], body['borrower']['username']
        )

        loan_delays = Table('trust_loan_delays')
        itgs.read_cursor.execute(
            Query.from_(loan_delays)
            .select(
                loan_delays.id,
                loan_delays.loans_completed_as_lender,
                loan_delays.min_review_at
            )
            .where(loan_delays.user_id == Parameter('%s'))
            .get_sql(),
            (body['lender']['id'],)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.TRACE,
                '/u/{} has no loan delay - finished',
                body['lender']['username']
            )
            return
        (
            loan_delay_id,
            loan_delay_loans_completed_as_lender,
            loan_delay_min_review_at
        ) = row

        loans = Table('loans')
        itgs.read_cursor.execute(
            Query.from_(loans)
            .select(Count(Star()))
            .where(loans.lender_id == Parameter('%s'))
            .where(loans.repaid_at.notnull())
            .get_sql(),
            (body['lender']['id'],)
        )
        (num_completed_as_lender,) = itgs.read_cursor.fetchone()

        if num_completed_as_lender < loan_delay_loans_completed_as_lender:
            itgs.logger.print(
                Level.TRACE,
                '/u/{} has a loan delay for {} loans. They are now at {} ' +
                'loans; nothing to do.',
                body['lender']['username'],
                loan_delay_loans_completed_as_lender,
                num_completed_as_lender
            )
            return

        usrs = Table('users')
        itgs.read_cursor.execute(
            Query.from_(usrs)
            .select(usrs.id)
            .where(usrs.username == Parameter('%s'))
            .get_sql(),
            ('loansbot',)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.write_cursor.execute(
                Query.into(usrs)
                .columns(usrs.username)
                .insert(Parameter('%s'))
                .returning(usrs.id)
                .get_sql(),
                ('loansbot',)
            )
            row = itgs.write_cursor.fetchone()

        (loansbot_user_id,) = row
        trust_comments = Table('trust_comments')
        itgs.write_cursor.execute(
            Query.into(trust_comments).columns(
                trust_comments.author_id,
                trust_comments.target_id,
                trust_comments.comment
            ).insert(*[Parameter('%s') for _ in range(3)])
            .get_sql(),
            (
                loansbot_user_id,
                body['lender']['id'],
                (
                    '/u/{} has reached {}/{} of the loans completed as lender for ' +
                    'review and has been added back to the trust queue.'
                ).format(
                    body['lender']['username'],
                    num_completed_as_lender,
                    loan_delay_loans_completed_as_lender
                )
            )
        )
        itgs.write_cursor.execute(
            Query.from_(loan_delays).delete()
            .where(loan_delays.id == Parameter('%s'))
            .get_sql(),
            (loan_delay_id,)
        )
        delqueue.store_event(
            itgs,
            delqueue.QUEUE_TYPES['trust'],
            max(datetime.now(), loan_delay_min_review_at),
            {'username': body['lender']['username'].lower()},
            commit=True
        )

        itgs.logger.print(
            Level.INFO,
            '/u/{} reached {}/{} of the loan delay loans completed as lender ' +
            'and has been added to the trust queue',
            body['lender']['username'],
            num_completed_as_lender,
            loan_delay_loans_completed_as_lender
        )
