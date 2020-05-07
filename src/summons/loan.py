"""Describes the summon for creating a loan between the comment author and the
thread author.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy


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
        token_vals = PARSER.parse(comment['body'])
        borrower_username = comment['link_author']
        lender_username = comment['author']

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': (
                    'Detected that /u/{} wants to lend /u/{} {}{}',
                    lender_username, borrower_username,
                    token_vals[0],
                    '' if token_vals[1] is None else f' but store it in {token_vals[1]}'
                )
            }
        )
