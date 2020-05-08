"""Describes the summon for checking the history of a particular user without
using the website. Includes a link to the appropriate page on the website.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy


PARSER = Parser(
    '$check',
    [
        {'token': parsing.ext_tokens.create_user_token(), 'optional': False},
    ]
)


class CheckSummon(Summon):
    def __init__(self):
        self.name = 'check'

    def might_apply_to_comment(self, comment):
        """Determines if the $check command might be in the comment

        Returns:
            True if $check is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        requester_username = comment['author']
        target_username = token_vals[0]

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': (
                    'Detected that /u/{} wants to check /u/{}'.format(
                        requester_username, target_username
                    )
                )
            }
        )