"""This runner is responsible for detecting when a moderator leaves the
subreddit and stripping them of most of their permissions and sending
them a farewell message thanking them for their contributions.
"""
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lblogging import Level
from lbshared.responses import get_letter_response
import utils.reddit_proxy
import utils.mod_onboarding_utils
from .utils import listen_event
from functools import partial
import time

LOGGER_IDEN = 'runners/mod_offboarding.py'
"""The identifier for this runner in the logs"""

FAREWELL_LETTER_NAME = 'mod_offboarding_farewell'
"""The message we send to moderators we offboarded"""


def main():
    version = time.time()

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'mods.removed', partial(handle_mod_removed, version))


def handle_mod_removed(version, event):
    with LazyItgs(logger_iden=LOGGER_IDEN, no_read_only=True) as itgs:
        itgs.logger.print(
            Level.DEBUG,
            'Detected that /u/{} is no longer a moderator',
            event['username']
        )

        utils.mod_onboarding_utils.revoke_mod_permissions(
            itgs, event['user_id'], commit=True
        )

        itgs.logger.print(
            Level.DEBUG,
            'Revoked moderator privileges from /u/{}, sending a farewell...',
            event['username']
        )

        (subject, body) = get_letter_response(
            itgs, FAREWELL_LETTER_NAME, username=event['username']
        )
        utils.reddit_proxy.send_request(
            itgs, 'mod_offboarding', version, 'compose',
            {
                'recipient': event['username'],
                'subject': subject,
                'body': body
            }
        )

        itgs.logger.print(
            Level.INFO,
            'Revoked moderator privileges from /u/{} and sent a farewell message',
            event['username']
        )
