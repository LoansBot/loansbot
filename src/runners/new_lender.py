"""This runner is responsible for scanning for new lenders and, when found,
sending a message to the moderators."""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
import time
from lbshared.money import Money
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Count
import utils.reddit_proxy
import json
from lbshared.responses import get_response


def main():
    version = time.time()

    with LazyIntegrations(logger_iden='runners/new_lender.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

        itgs.channel.exchange_declare(
            'events',
            'topic'
        )

        consumer_channel = itgs.channel()
        queue_declare_result = consumer_channel.queue_declare('', exclusive=True)
        queue_name = queue_declare_result.method.queue

        consumer_channel.queue_bind(queue_name, 'events', 'loans.create')
        consumer = consumer_channel.consume(queue_name, inactivity_timeout=600)
        for method_frame, props, body_bytes in consumer:
            if method_frame is None:
                pass
            body_str = body_bytes.decode('utf-8')
            body = json.loads(body_str)
            handle_loan_create(version, body)
            consumer_channel.basic_ack(method_frame.delivery_tag)
        consumer.cancel()


def handle_loan_create(version, event):
    """Handle a loan create event from the events queue.

    Arguments:
        version (any): The version to pass to the reddit proxy
        event (dict): Describes the loan
            loan_id (int): The id of the loan that was generated
            comment (dict): The comment that generated the loan.
                link_fullname (str): The fullname of the link the comment is in
                fullname (str): The fullname of the comment
            lender (dict): The lender
                id (int): The id of the user in our database
                username (str): The username for the lender
            borrower (dict): The borrower
                id (int): The id of the user in our database
                username (str): The username for the borrower
            amount (dict): The amount of money transfered. Has the same keys as
                the Money object has attributes.
                minor (int)
                currency (int)
                exp (int)
                symbol (str, None)
                symbol_on_left (bool)
            permalink (str): A permanent link to the loan.
    """
    with LazyIntegrations(logger_iden='runners/new_lender.py#handle_loan_create') as itgs:
        itgs.logger.trace(
            'Detected loan from /u/{} to /u/{}',
            event['lender']['username'], event['borrower']['username']
        )
        amount = Money(**event['amount'])

        loans = Table('loans')
        itgs.read_cursor.execute(
            Query.from_(loans)
            .select(Count('*'))
            .where(loans.lender_id == Parameter('%s'))
            .where(loans.id < Parameter('%s'))
            .get_sql(),
            (event['lender']['id'], event['loan_id'])
        )
        (num_previous_loans,) = itgs.read_cursor.fetchone()

        if num_previous_loans > 0:
            itgs.logger.print(
                Level.TRACE,
                (
                    'Ignoring the loan by /u/{} to /u/{} - /u/{} has {} ' +
                    'previous loans, so they are not new'
                ),
                event['lender']['username'], event['borrower']['username'],
                event['lender']['username'], num_previous_loans
            )
            return

        itgs.logger.print(
            Level.INFO,
            '/u/{} just made his first loan as lender. Messaging the mods.',
            event['lender']['username']
        )

        formatted_body = get_response(
            itgs,
            'new_lender',
            lender_username=event['lender']['username'],
            borrower_username=event['borrower']['username'],
            amount=amount,
            permalink=event['permalink']
        )

        utils.reddit_proxy.send_request(
            itgs, 'new_lender', version, 'compose',
            {
                'recipient': '/r/borrow',
                'subject': 'New Lender: /u/{}'.format(event['lender']['username']),
                'body': formatted_body
            }
        )
