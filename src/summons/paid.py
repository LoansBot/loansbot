"""Describes the summon for marking that a particular user has repaid them a
certain amount of money. This will apply it toward the principal of the
borrowers loan to that lender in oldest-first order, rolling funds over.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy


PARSER = Parser(
    '$paid',
    [
        {'token': parsing.ext_tokens.create_user_token(), 'optional': False},
        {'token': parsing.ext_tokens.create_money_token(), 'optional': False}
    ]
)


class PaidSummon(Summon):
    def __init__(self):
        self.name = 'paid'

    def might_apply_to_comment(self, comment):
        """Determines if the $paid command might be in the comment

        Returns:
            True if $paid is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        lender_username = comment['author']
        borrower_username = token_vals[0]
        amt = token_vals[1]

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': (
                    'Detected that /u/{} was repaid {} by /u/{}'.format(
                        lender_username, amt, borrower_username
                    )
                )
            }
        )
