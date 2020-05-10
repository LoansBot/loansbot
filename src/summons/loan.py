"""Describes the summon for creating a loan between the comment author and the
thread author.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy
import convert
import money
import time
import query_helper
from lbshared.responses import get_response
from pypika import Query, Table, Parameter


PARSER = Parser(
    '$loan',
    [
        {'token': parsing.ext_tokens.create_money_token(), 'optional': False},
        {'token': parsing.ext_tokens.as_currency_token(), 'optional': True}
    ]
)


class LoanSummon(Summon):
    def __init__(self):
        self.name = 'loan'

    def might_apply_to_comment(self, comment):
        """Determines if the $loan command might be in the comment

        Returns:
            True if $loan is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        start_at = time.time()
        token_vals = PARSER.parse(comment['body'])
        borrower_username = comment['link_author']
        lender_username = comment['author']
        amount = token_vals[0]
        store_currency = token_vals[1] or amount.currency

        if amount.currency == store_currency:
            store_amount = amount
            rate = 1
        else:
            rate = convert.convert(itgs, amount.currency, store_currency)
            store_amount = money.Money(int(amount.minor * rate), store_currency)

        if store_currency == 'USD':
            usd_amount = store_amount
            usd_rate = 1
        else:
            # Where possible we want the source to be consistent rather than
            # the target as it allows us to reuse requests
            usd_rate = 1 / convert.convert(itgs, 'USD', store_currency)
            usd_amount = money.Money(int(store_amount.minor * usd_rate), 'USD')

        users = Table('users')
        currencies = Table('currencies')
        moneys = Table('moneys')
        loans = Table('loans')
        (lender_user_id,) = query_helper.find_or_create_or_find(
            itgs,
            (
                Query.from_(users)
                .select(users.id)
                .where(users.username == Parameter('%s'))
                .get_sql(),
                (lender_username.lower(),)
            ),
            (
                Query.into(users)
                .columns(users.username)
                .values(Parameter('%s'))
                .returning(users.id)
                .get_sql(),
                (lender_username.lower(),)
            )
        )
        (borrower_user_id,) = query_helper.find_or_create_or_find(
            itgs,
            (
                Query.from_(users)
                .select(users.id)
                .where(users.username == Parameter('%s'))
                .get_sql(),
                (borrower_username.lower(),)
            ),
            (
                Query.into(users)
                .columns(users.username)
                .values(Parameter('%s'))
                .returning(users.id)
                .get_sql(),
                (borrower_username.lower(),)
            )
        )
        (
            db_store_currency_id,
            db_currency_symbol,
            db_currency_sym_on_left
        ) = query_helper.find_or_create_or_find(
            itgs,
            (
                Query.from_(currencies)
                .select(currencies.id, currencies.symbol, currencies.symbol_on_left)
                .where(currencies.code == Parameter('%s'))
                .get_sql(),
                (store_currency,)
            ),
            (
                Query.into(currencies)
                .columns(
                    currencies.code,
                    ' ' + currencies.symbol,
                    currencies.symbol_on_left,
                    currencies.exponent
                )
                .insert_query(*[Parameter('%s') for _ in range(4)])
                .returning(currencies.id, currencies.symbol, currencies.symbol_on_left)
                .get_sql(),
                (
                    currencies.code,
                    currencies.code,
                    False,
                    money.ISO_CODES_TO_EXP[currencies.code]
                )
            )
        )
        itgs.write_cursor.execute(
            Query.into(moneys)
            .columns(moneys.currency_id, moneys.amount, moneys.amount_usd_cents)
            .insert(*[Parameter('%s') for _ in range(4)])
            .returning(moneys.id)
            .get_sql(),
            (
                db_store_currency_id,
                store_amount,
                usd_amount
            )
        )
        (principal_id,) = itgs.write_cursor.fetchone()
        itgs.write_cursor.execute(
            Query.into(moneys)
            .columns(moneys.currency_id, moneys.amount, moneys.amount_usd_cents)
            .insert(*[Parameter('%s') for _ in range(4)])
            .returning(moneys.id)
            .get_sql(),
            (
                db_store_currency_id,
                0,
                0
            )
        )
        (principal_repayment_id,) = itgs.write_cursor.fetchone()
        itgs.write_cursor.execute(
            Query.into(loans)
            .columns(
                loans.lender_id,
                loans.borrower_id,
                loans.principal_id,
                loans.principal_repayment_id,
                loans.repaid_at,
                loans.unpaid_at,
                loans.deleted_at
            ).values(*[Parameter('%s') for _ in range(7)])
            .returning(loans.id)
            .get_sql(),
            (
                lender_user_id,
                borrower_user_id,
                principal_id,
                principal_repayment_id,
                None,
                None,
                None
            )
        )
        (loan_id,) = itgs.write_cursor.fetchone()
        itgs.write_conn.commit()

        pretty_store_amount = (
            '{symbol}{major}' if db_currency_sym_on_left else '{major}{symbol}'
        ).format(symbol=db_currency_symbol, major=store_amount.major_str())

        processing_time = time.time() - start_at
        (formatted_response,) = get_response(
            itgs,
            'successful_loan',
            lender_username=lender_username,
            borrower_username=borrower_username,
            principal=pretty_store_amount,
            principal_explicit=store_amount,
            loan_id=loan_id,
            processing_time=processing_time
        )

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': formatted_response
            }
        )
