"""Describes the summon for marking that a particular loan, identified by its
id, has had a repayment. This may only be a partial repayment.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy


PARSER = Parser(
    '$paid_with_id',
    [
        {'token': parsing.ext_tokens.create_uint_token(), 'optional': False},
        {'token': parsing.ext_tokens.create_money_token(), 'optional': False}
    ]
)


class PaidWithIdSummon(Summon):
    def __init__(self):
        self.name = 'paid_with_id'

    def might_apply_to_comment(self, comment):
        """Determines if the $paid_with_id command might be in the comment

        Returns:
            True if $paid_with_id is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        lender_username = comment['author']
        loan_id = token_vals[0]
        amt = token_vals[1]

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': (
                    'Detected that /u/{} was repaid {} for loan #{}'.format(
                        lender_username, amt, loan_id
                    )
                )
            }
        )
