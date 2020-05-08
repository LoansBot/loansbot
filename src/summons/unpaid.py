"""Describes the summon for marking that a particular user is delinquent. All
the loans from that user to the lender will be marked as unpaid.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy


PARSER = Parser(
    '$unpaid',
    [
        {'token': parsing.ext_tokens.create_user_token(), 'optional': False}
    ]
)


class UnpaidSummon(Summon):
    def __init__(self):
        self.name = 'unpaid'

    def might_apply_to_comment(self, comment):
        """Determines if the $unpaid command might be in the comment

        Returns:
            True if $unpaid is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        lender_username = comment['author']
        borrower_username = token_vals[0]

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': (
                    'Detected that /u/{} marked /u/{} as delinquent'.format(
                        lender_username, borrower_username
                    )
                )
            }
        )
