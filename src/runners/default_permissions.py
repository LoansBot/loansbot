"""This runner listens for users signing up via the website and assigns them
the default permissions.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
from pypika import PostgreSQLQuery as Query, Table, Parameter
from .utils import listen_event
import utils.perm_utils
from functools import partial
import time
import os


LOGGER_IDEN = 'runners/default_permissions.py'
"""The identifier for this runner in the logs"""

DEFAULT_PERMISSIONS = tuple(os.getenv('DEFAULT_PERMISSIONS', '').split(','))
"""The list of permissions we grant to new users when they sign up"""


def main():
    version = time.time()

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'user.signup', partial(handle_user_signup, version))


def handle_user_signup(version, body):
    """Called when we detect that a user has just signed up. Assigns their
    human authentication method some default permissions.

    Arguments:
    - `version (float)`: Our version string when using the reddit proxy.
    - `body (dict)`: The event body. Has the following keys:
      - `user_id (int)`: The id of the user who just signed up.
    """
    with LazyIntegrations(logger_iden=LOGGER_IDEN, no_read_only=True) as itgs:
        itgs.logger.print(
            Level.TRACE,
            'Detected user signup: id={}',
            body['user_id']
        )

        usrs = Table('users')
        itgs.read_cursor.execute(
            Query.from_(usrs)
            .select(usrs.username)
            .where(usrs.id == Parameter('%s'))
            .get_sql(),
            (body['user_id'],)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.WARN,
                'Race condition detected! Got user signup event for user id {} '
                + 'but that user is not in the database. They will not receive '
                + 'the expected default permissions.',
                body['user_id']
            )
            return
        (username,) = row

        passwd_auths = Table('password_authentications')
        itgs.read_cursor.execute(
            Query.from_(passwd_auths)
            .select(passwd_auths.id)
            .where(passwd_auths.user_id == Parameter('%s'))
            .where(passwd_auths.human.eq(True))
            .get_sql(),
            (body['user_id'],)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.WARN,
                'Race condition detected! Got user signup event for user id {} '
                + 'which corresponds to user /u/{} but that user does not have a '
                + 'password set! They will not get the default permissions.',
                body['user_id'], username
            )
            return

        (passwd_auth_id,) = row

        if not DEFAULT_PERMISSIONS:
            itgs.logger.print(
                Level.DEBUG,
                'No default permissions -> nothing to do for /u/{}',
                username
            )
            return

        perms = Table('permissions')
        itgs.read_cursor.execute(
            Query.from_(perms)
            .select(perms.id)
            .where(perms.name.isin(tuple(Parameter('%s') for _ in DEFAULT_PERMISSIONS)))
            .get_sql(),
            DEFAULT_PERMISSIONS
        )

        perm_ids_to_grant = []
        row = itgs.read_cursor.fetchone()
        while row is not None:
            perm_ids_to_grant.append(row[0])
            row = itgs.read_cursor.fetchone()

        if len(perm_ids_to_grant) != len(DEFAULT_PERMISSIONS):
            itgs.logger.print(
                Level.WARN,
                'DEFAULT_PERMISSIONS has {} entries ({}), but it only maps '
                'to {} actual permissions ({})!',
                len(DEFAULT_PERMISSIONS), DEFAULT_PERMISSIONS,
                len(perm_ids_to_grant), perm_ids_to_grant
            )
            if not perm_ids_to_grant:
                return

        utils.perm_utils.grant_permissions(
            itgs, body['user_id'], 'Default permissions on signup', passwd_auth_id,
            perm_ids_to_grant, commit=True
        )

        itgs.logger.print(
            Level.INFO,
            '/u/{} just signed up and was granted default permissions',
            username
        )
