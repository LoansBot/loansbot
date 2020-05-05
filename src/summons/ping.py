"""Describes a simple ping summon, which has the format `$ping` and th Loansbot
responds `Pong!`. This is a useful way of verifying the LoansBot is correctly
scanning reddit for comments and that one can interact with the LoansBot.
"""
from .summon import Summon
import utils.reddit_proxy


class PingSummon(Summon):
    def __init__(self):
        self.name = 'ping'

    def might_apply_to_comment(self, comment):
        """Determines if the $ping command is in the comment

        Returns:
            True if $ping is in the comment, false otherwise
        """
        return '$ping' in comment['body']

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': 'Pong!'
            }
        )
