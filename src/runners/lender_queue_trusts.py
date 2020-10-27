"""This runner is responsible for initializing a trust status of unknown and
adding a user to the trust queue when they reach a threshold of loans completed
as lender.
"""
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lblogging import Level
from .utils import listen_event
import lbshared.delayed_queue as delayed_queue
from lbshared.responses import get_letter_response
import utils.reddit_proxy
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Count
from pypika.terms import Star
from functools import partial
from datetime import datetime
import time

LOGGER_IDEN = 'runners/lender_queue_trusts.py'
THRESHOLD_LOANS = 15


def main():
    version = time.time()
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'loans.paid', partial(handle_loan_paid, version))


def handle_loan_paid(version, event):
    """Called shortly after a loan is paid.
    """
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(
            Level.TRACE,
            'Detected /u/{} had a payment toward one of the loans he gave out...',
            event['lender']['username']
        )

        trusts = Table('trusts')
        itgs.read_cursor.execute(
            Query.from_(trusts)
            .select(1)
            .where(trusts.user_id == Parameter('%s'))
            .get_sql(),
            (event['lender']['id'],)
        )
        if itgs.read_cursor.fetchone():
            itgs.logger.print(
                Level.TRACE,
                '/u/{} already has a trust entry - nothing to do',
                event['lender']['username']
            )
            return

        loans = Table('loans')
        itgs.read_cursor.execute(
            Query.from_(loans)
            .select(Count(Star()))
            .where(loans.lender_id == Parameter('%s'))
            .where(loans.repaid_at.notnull())
            .where(loans.deleted_at.isnull())
            .get_sql(),
            (event['lender']['id'],)
        )
        (loans_compl_as_lender,) = itgs.read_cursor.fetchone()

        if loans_compl_as_lender < THRESHOLD_LOANS:
            itgs.logger.print(
                Level.DEBUG,
                '/u/{} now has {} loans completed as lender, which is below threshold of {}',
                event['lender']['username'], loans_compl_as_lender, THRESHOLD_LOANS
            )
            return

        itgs.logger.print(
            Level.DEBUG,
            '/u/{} reached threshold of {} loans completed as lender, '
            'which is above the threshold of {}, queuing trust entry...',
            event['lender']['username'], loans_compl_as_lender, THRESHOLD_LOANS
        )
        itgs.write_cursor.execute(
            Query.into(trusts)
            .columns(trusts.user_id, trusts.status, trusts.reason)
            .insert(*(Parameter('%s') for _ in range(3)))
            .get_sql(),
            (event['lender']['id'], 'unknown', 'Vetting required')
        )
        delayed_queue.store_event(
            itgs,
            delayed_queue.QUEUE_TYPES['trust'],
            datetime.now(),
            {'username': event['lender']['username'].lower()},
            commit=True
        )
        itgs.logger.print(
            Level.INFO,
            'Gave /u/{} an explicit unknown status and added to trust queue',
            event['lender']['username']
        )

        (subject, body) = get_letter_response(
            itgs, 'queue_trust_pm', username=event['lender']['username']
        )

        utils.reddit_proxy.send_request(
            itgs, 'recheck_permission', version, 'compose',
            {
                'recipient': '/r/borrow',
                'subject': subject,
                'body': body
            }
        )

        itgs.logger.print(
            Level.TRACE,
            'Successfully alerted modmail of the new entry in trust queue'
        )
