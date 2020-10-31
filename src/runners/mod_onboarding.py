"""This runner is responsible for listening for new moderators, granting them
extensive permissions to the website, and then send them a greeting to let them
know we've detected their account. If the moderator has not yet claimed their
account this instead just sends them a message to claim their account, and the
permissions will be granted in the runner runners/mod_onboarding_claim
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

LOGGER_IDEN = 'runners/mod_onboarding'
GREETING_LETTER_NAME = 'mod_onboarding_greeting'
ACCOUNT_NOT_CLAIMED_LETTER_NAME = 'mod_onboarding_unclaimed'


def main():
    version = time.time()

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'mods.added', partial(handle_mod_added, version))


def handle_mod_added(version, event):
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(
            Level.DEBUG,
            'Detected that /u/{} is now a moderator',
            event['username']
        )

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
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.DEBUG,
                'Detected that /u/{} has not yet claimed his account',
                event['username']
            )
            (subject, body) = get_letter_response(
                itgs, ACCOUNT_NOT_CLAIMED_LETTER_NAME, username=event['username']
            )
            utils.reddit_proxy.send_request(
                itgs, 'mod_onboarding', version, 'compose',
                {
                    'recipient': event['username'],
                    'subject': subject,
                    'body': body
                }
            )
            utils.mod_onboarding_utils.store_letter_message(
                itgs, event['user_id'], ACCOUNT_NOT_CLAIMED_LETTER_NAME, commit=True
            )
            itgs.logger.print(
                Level.INFO,
                'Sent a message to /u/{} to claim his account to gain mod '
                'permissions on the website (since he is now a mod on the '
                'subreddit)',
                event['username']
            )
            return

        (passwd_auth_id,) = row
        utils.mod_onboarding_utils.grant_mod_permissions(
            itgs, event['user_id'], passwd_auth_id, commit=True
        )

        itgs.logger.print(
            Level.DEBUG,
            'Granted all permissions to /u/{}, sending greeting...',
            event['username']
        )
        (subject, body) = get_letter_response(
            itgs, GREETING_LETTER_NAME, username=event['username']
        )
        utils.reddit_proxy.send_request(
            itgs, 'mod_onboarding', version, 'compose',
            {
                'recipient': event['username'],
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
            event['username']
        )
