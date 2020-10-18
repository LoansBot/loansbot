"""This runner is responsible for listening to users loans getting marked unpaid
and banning the borrower.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
from lbshared.responses import get_response
import perms.manager
import utils.reddit_proxy
from pypika import PostgreSQLQuery as Query, Table, Parameter
import time
import json

LOGGER_IDEN = 'runners/ban_unpaid.py'
RPIDEN = 'ban_unpaid'


def main():
    version = time.time()

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')
        # Close logger

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.channel.exchange_declare(
            'events',
            'topic'
        )

        consumer_channel = itgs.amqp.channel()
        queue_declare_result = consumer_channel.queue_declare('', exclusive=True)
        queue_name = queue_declare_result.method.queue
        consumer_channel.queue_bind(queue_name, 'events', 'loans.unpaid')
        consumer = consumer_channel.consume(queue_name, inactivity_timeout=600)
        for method_frame, props, body_bytes in consumer:
            if method_frame is None:
                continue
            body_str = body_bytes.decode('utf-8')
            body = json.loads(body_str)
            handle_loan_unpaid(version, body)
            consumer_channel.basic_ack(method_frame.delivery_tag)
        consumer.cancel()


def handle_loan_unpaid(version, body):
    loan_unpaid_event_id = body['loan_unpaid_event_id']

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Detected loan unpaid event: {}', loan_unpaid_event_id)
        loan_unpaid_events = Table('loan_unpaid_events')
        loans = Table('loans')
        usrs = Table('users')
        borrowers = usrs.as_('borrowers')
        lenders = usrs.as_('lenders')

        itgs.read_cursor.execute(
            Query.from_(loan_unpaid_events)
            .join(loans).on(loans.id == loan_unpaid_events.loan_id)
            .join(borrowers).on(borrowers.id == loans.borrower_id)
            .select(borrowers.username, lenders.username)
            .where(loan_unpaid_events.id == Parameter('%s'))
            .get_sql(),
            (loan_unpaid_event_id,)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.WARN, 'Loan unpaid event {} did not exist!', loan_unpaid_event_id)
            return
        (username, lender_username) = row
        itgs.logger.print(
            Level.TRACE,
            'Ensuring /u/{} is moderator or banned from unpaid event {}',
            username, loan_unpaid_event_id
        )
        info = perms.manager.fetch_info(itgs, username, RPIDEN, version)
        if info is None:
            itgs.logger.print(
                Level.INFO,
                '/u/{} defaulted on a loan then deleted their account.',
                username
            )
            return
        if info['borrow_banned']:
            itgs.logger.print(
                Level.DEBUG,
                '/u/{} defaulted on a loan but they are already banned.',
                username
            )
            return
        if info['borrow_moderator']:
            itgs.logger.print(
                Level.INFO,
                '/u/{} defaulted on a loan but is a moderator - no ban',
                username
            )
            return
        if info['borrow_approved_submitter']:
            itgs.logger.print(
                Level.INFO,
                '/u/{} defaulted on a loan but is an approved submitter - no ban',
                username
            )
            # easy to forget about approved submitters
            utils.reddit_proxy.send_request(
                itgs, RPIDEN, version, 'compose',
                {
                    'recipient': '/r/borrow',
                    'subject': 'Approved Submitter Unpaid Loan',
                    'body': (
                        '/u/{} defaulted on a loan but did not get banned since they are '
                        + 'an approved submitter.'
                    ).format(username)
                }
            )
            return

        itgs.logger.print(
            Level.TRACE,
            'Banning /u/{} because they defaulted on a loan',
            username
        )

        substitutions = {
            'borrower_username': username,
            'lender_username': lender_username
        }

        utils.reddit_proxy.send_request(
            itgs, RPIDEN, version, 'ban_user',
            {
                'subreddit': 'borrow',
                'username': username,
                'message': get_response(itgs, 'unpaid_ban_message', **substitutions),
                'note': get_response(itgs, 'unpaid_ban_note', **substitutions)
            }
        )
        itgs.logger.print(
            Level.INFO,
            'Banned /u/{} on /r/borrow - failed to repay loan with /u/{}',
            username,
            lender_username
        )
        perms.manager.flush_cache(itgs, username)
