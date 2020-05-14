"""Describes the summon for confirming a payment as a borrower. This summon
is optional and is meant to protect the lender from the borrower later claiming
they did not get any funds.
"""
from .summon import Summon
from parsing.parser import Parser
from pypika import PostgreSQLQuery as Query, Table, Parameter, Order
import parsing.ext_tokens
import utils.reddit_proxy
from convert import convert
from money import Money
from lbshared.responses import get_response


PARSER = Parser(
    '$confirm',
    [
        {'token': parsing.ext_tokens.create_user_token(), 'optional': False},
        {'token': parsing.ext_tokens.create_money_token(), 'optional': False}
    ]
)


class ConfirmSummon(Summon):
    def __init__(self):
        self.name = 'confirm'

    def might_apply_to_comment(self, comment):
        """Determines if the $confirm command might be in the comment

        Returns:
            True if $confirm is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        borrower_username = comment['author']
        lender_username = token_vals[0]
        amt = token_vals[1]

        usd_amount = None
        if amt.currency == 'USD':
            usd_amount = amt
        else:
            # We prefer the source is stable so we get the inverted rate and invert
            usd_rate = 1 / convert(itgs, 'USD', amt.currency)
            usd_amount = Money(
                int(amt.minor * usd_rate), 'USD',
                exp=2, symbol='$', symbol_on_left=True
            )

        loans = Table('loans')
        users = Table('users')
        lenders = users.as_('lenders')
        borrowers = users.as_('borrowers')
        loan_creation_infos = Table('loan_creation_infos')
        moneys = Table('moneys')
        principals = moneys.as_('principals')
        currencies = Table('currencies')
        principal_currencies = currencies.as_('principal_currencies')
        principal_repayments = moneys.as_('principal_repayments')

        itgs.read_cursor.execute(
            Query.from_(loans)
            .select(
                loans.id,
                loan_creation_infos.parent_fullname,
                loan_creation_infos.comment_fullname
            )
            .join(loan_creation_infos)
            .on(loan_creation_infos.loan_id == loans.id)
            .join(lenders)
            .on(lenders.id == loans.lender_id)
            .join(borrowers)
            .on(borrowers.id == loans.borrower_id)
            .join(principals)
            .on(principals.id == loans.principal_id)
            .join(principal_currencies)
            .on(principal_currencies.id == principals.currency_id)
            .join(principal_repayments)
            .on(principal_repayments.id == loans.principal_repayment_id)
            .where(lenders.username == Parameter('%s'))
            .where(borrowers.username == Parameter('%s'))
            .where(principal_repayments.amount == 0)
            .where(loans.unpaid_at.isnull())
            .where(loans.deleted_at.isnull())
            .where(
                (
                    (principal_currencies.code == amt.currency)
                    & (principals.amount == amt.minor)
                ) | (
                    (principal_currencies.code != amt.currency)
                    & (principals.amount <= (usd_amount.minor + 100))
                )
            )
            .orderby(loans.created_at, order=Order.desc)
            .limit(1)
            .get_sql(),
            (lender_username.lower(), borrower_username.lower())
        )
        row = itgs.read_cursor.fetchone()

        if row is None:
            formatted_response = get_response(
                itgs,
                'confirm_no_loan',
                borrower_username=borrower_username,
                lender_username=lender_username,
                amount=amt,
                usd_amount=usd_amount
            )
        else:
            (loan_id, parent_fullname, comment_fullname) = row
            formatted_response = get_response(
                itgs,
                'confirm',
                borrower_username=borrower_username,
                lender_username=lender_username,
                amount=amt,
                usd_amount=usd_amount,
                loan_permalink=(
                    'https://reddit.com'
                    if parent_fullname is None
                    else
                    'https://reddit.com/comments/{}/redditloans/{}'.format(
                        parent_fullname, comment_fullname
                    )
                ),
                loan_id=loan_id
            )

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': formatted_response
            }
        )
