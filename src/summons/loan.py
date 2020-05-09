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

        processing_time = time.time() - start_at
        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': (
                    (
                        'Detected that /u/{} wants to lend /u/{} {}{}. ' +
                        'The stored amount is {} (rate used: {}) and the USD ' +
                        'reference amount is {} (rate used: {}). It took ' +
                        '{:.3f} seconds to perform summon processing on this ' +
                        'request.'
                    ).format(
                        lender_username, borrower_username, amount,
                        '' if store_currency is None else f' but store it in {store_currency}',
                        store_amount, rate, usd_amount, usd_rate, processing_time
                    )
                )
            }
        )
