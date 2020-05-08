"""Describes the summon for confirming a payment as a borrower. This summon
is optional and is meant to protect the lender from the borrower later claiming
they did not get any funds.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy


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

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': (
                    'Detected that /u/{} wants to confirm /u/{} sent him {}'.format(
                        borrower_username, lender_username, amt
                    )
                )
            }
        )
