"""This runner is responsible for listening to a moderator claiming their
account. When it detects this it grants them extensive privileges and sends
them a message to let them know.
"""

from pypika import PostgreSQLQuery as Query, Table, Parameter
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lblogging import Level
from lbshared.responses import get_letter_response
import utils.reddit_proxy
import utils.mod_onboarding_utils
from .utils import listen_event
from functools import partial
import time

LOGGER_IDEN = 'runners/mod_onboarding_claim'
GREETING_LETTER_NAME = 'mod_onboarding_claim_greeting'


def main():
    version = time.time()

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'user.signup', partial(handle_account_claimed, version))


def handle_account_claimed(version, event):
    """Called when we detect that a user has just signed up. If they are a
    moderator this will grant them all the appropriate permissions, otherwise
    this does nothing.

    Arguments:
    - `version (float)`: Our version string when using the reddit proxy.
    - `event (dict)`: The event body. Has the following keys:
      - `user_id (int)`: The id of the user who just signed up.
    """
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(
            Level.TRACE,
            'Detected that user {} just claimed their account',
            event['user_id']
        )

        usrs = Table('users')
        itgs.read_cursor.execute(
            Query.from_(usrs)
            .select(usrs.username)
            .where(usrs.id == Parameter('%s'))
            .get_sql(),
            (event['user_id'],)
        )
        (username,) = itgs.read_cursor.fetchone()

        itgs.logger.print(
            Level.TRACE,
            'Detected that user {} is /u/{}',
            event['user_id'], username
        )

        moderators = Table('moderators')
        itgs.read_cursor.execute(
            Query.from_(moderators)
            .select(1)
            .where(moderators.user_id == Parameter('%s'))
            .get_sql(),
            (event['user_id'],)
        )
        if itgs.read_cursor.fetchone() is None:
            itgs.logger.print(
                Level.TRACE,
                'Detected that /u/{} is not a moderator',
                username
            )
            return

        itgs.logger.print(
            Level.DEBUG,
            'Detected that the moderator /u/{} just claimed his account',
            username
        )

        # We just sleep off the race condition with default_permissions to avoid
        # having to deal with concurrent modification of password_authentications
        time.sleep(3)

        password_authentications = Table('password_authentications')
        itgs.read_cursor.execute(
            Query.from_(password_authentications)
            .select(password_authentications.id)
            .where(password_authentications.user_id == Parameter('%s'))
            .where(password_authentications.human.eq(True))
            .where(password_authentications.deleted.eq(False))
            .get_sql(),
            (event['user_id'],)
        )
        (passwd_auth_id,) = itgs.read_cursor.fetchone()

        utils.mod_onboarding_utils.grant_mod_permissions(
            itgs, event['user_id'], passwd_auth_id, commit=True
        )

        itgs.logger.print(
            Level.DEBUG,
            'Granted all permissions to /u/{}, sending greeting...',
            username
        )
        (subject, body) = get_letter_response(
            itgs, GREETING_LETTER_NAME, username=username
        )
        utils.reddit_proxy.send_request(
            itgs, 'mod_onboarding_claim', version, 'compose',
            {
                'recipient': username,
                'subject': subject,
                'body': body
            }
        )
        utils.mod_onboarding_utils.store_letter_message(
            itgs, event['user_id'], GREETING_LETTER_NAME, commit=True
        )
        itgs.logger.print(
            Level.INFO,
            'Granted all permissions to the new mod /u/{} & sent a greeting',
            username
        )
