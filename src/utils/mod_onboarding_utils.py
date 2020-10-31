"""These utility functions are related to moderator onboarding, which is split
across several runners.
"""
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.terms import Not
from lbshared.pypika_crits import ExistsCriterion
from .perm_utils import grant_permissions, revoke_permissions
import typing
import os

if typing.TYPE_CHECKING:
    from lbshared.lazy_integrations import LazyIntegrations as LazyItgs


DEFAULT_PERMISSIONS = tuple(os.getenv('DEFAULT_PERMISSIONS', '').split(','))
"""The list of permissions we grant to new users when they sign up"""


def store_letter_message(itgs: 'LazyItgs', user_id: int, letter_name: str, commit=False):
    """This function is responsible for storing that we sent an onboarding
    letter message to the given user, where the subject and body were
    fetched as if by `lbshared.responses.get_letter_response`

    Arguments:
    - `itgs (LazyItgs)`: The integrations to use to connect to networked
      components.
    - `user_id (int)`: The id of the user who we sent the message to
    - `letter_name (str)`: The base part of the response for both the title and
      subject. The title response name is formed by appending `_title` and the
      subject is formed by appending `_body`
    - `commit (bool)`: True to commit the change immediately, false not to
    """
    (body_name, title_name) = (f'{letter_name}_body', f'{letter_name}_title')

    responses = Table('responses')
    itgs.read_cursor.execute(
        Query.from_(responses)
        .select(responses.id, responses.name)
        .where(responses.name.isin((Parameter('%s'), Parameter('%s'))))
        .get_sql(),
        (body_name, title_name)
    )
    rows = itgs.read_cursor.fetchall()
    if len(rows) != 2:
        raise Exception(f'expected 2 rows for letter base {letter_name}, got {len(rows)}')

    (body_id, title_id) = [r[0] for r in sorted(rows, key=lambda x: x[1])]

    mod_onboarding_msg_history = Table('mod_onboarding_msg_history')
    itgs.write_cursor.execute(
        Query.into(mod_onboarding_msg_history)
        .columns(
            mod_onboarding_msg_history.user_id,
            mod_onboarding_msg_history.title_response_id,
            mod_onboarding_msg_history.title_response_name,
            mod_onboarding_msg_history.body_response_id,
            mod_onboarding_msg_history.body_response_name
        )
        .insert(*(Parameter('%s') for _ in range(5)))
        .get_sql(),
        (user_id, title_id, title_name, body_id, body_name)
    )
    if commit:
        itgs.write_conn.commit()


def grant_mod_permissions(itgs: 'LazyItgs', user_id: int, passwd_auth_id: int, commit=False):
    """This function grants the given user all the permissions that moderators
    should have on the given password authentication id. This will handle
    updating the audit tables.

    Arguments:
    - `itgs (LazyItgs)`: The lazy integrations to use
    - `user_id (int)`: The id of the user we are granting mod permissions on
    - `passwd_auth_id (int)`: The id of the password authentication we are
      granting permissions.
    - `commit (bool)`: True to commit the transaction, false not to.
    """
    permissions = Table('permissions')
    passwd_auth_perms = Table('password_auth_permissions')
    itgs.read_cursor.execute(
        Query.from_(permissions)
        .select(permissions.id)
        .where(
            Not(
                ExistsCriterion(
                    Query.from_(passwd_auth_perms)
                    .where(passwd_auth_perms.password_authentication_id == Parameter('%s'))
                    .where(passwd_auth_perms.permission_id == permissions.id)
                    .get_sql()
                )
            )
        )
    )
    perm_ids_to_grant = []
    row = itgs.read_cursor.fetchone()
    while row is not None:
        (row_id,) = row
        perm_ids_to_grant.append(row_id)
        row = itgs.read_cursor.fetchone()

    if not perm_ids_to_grant:
        return

    grant_permissions(
        itgs,
        user_id,
        'Became moderator',
        passwd_auth_id,
        perm_ids_to_grant,
        commit=commit
    )


def revoke_mod_permissions(itgs: LazyItgs, user_id: int, commit=False):
    """This function revokes all non-default permissions on the given user
    because they are no longer a moderator. This will apply to all
    authentication methods and will log them out. This will handle updating the
    audit tables.

    Arguments:
    - `itgs (LazyItgs)`: The integrations to use for networked services
    - `user_id (int)`: The id of the user who is no longer a moderator
    - `commit (bool)`: True to commit the transaction, false not to
    """
    permissions = Table('permissions')
    passwd_auths = Table('password_authentications')
    passwd_auth_perms = Table('password_auth_permissions')

    itgs.read_cursor.execute(
        Query.from_(passwd_auths)
        .select(passwd_auths.id)
        .where(passwd_auths.user_id == Parameter('%s'))
        .where(passwd_auths.deleted.eq(False))
        .get_sql(),
        (user_id,)
    )

    passwd_auth_ids = []
    row = itgs.read_cursor.fetchone()
    while row is not None:
        passwd_auth_ids.append(row[0])
        row = itgs.read_cursor.fetchone()

    for passwd_auth_id in passwd_auth_ids:
        query = (
            Query.from_(passwd_auth_perms)
            .select(passwd_auth_perms.permission_id)
            .where(passwd_auth_perms.password_authentication_id == Parameter('%s'))
        )
        if DEFAULT_PERMISSIONS:
            query = (
                query
                .join(permissions).on(permissions.id == passwd_auth_perms.permission_id)
                .where(permissions.name.notin(*(Parameter('%s') for _ in DEFAULT_PERMISSIONS)))
            )

        itgs.read_cursor.execute(
            query.get_sql(),
            (passwd_auth_id, *DEFAULT_PERMISSIONS)
        )
        perm_ids_to_revoke = []
        row = itgs.read_cursor.fetchone()
        while row is not None:
            perm_ids_to_revoke.append(row[0])
            row = itgs.read_cursor.fetchone()

        if perm_ids_to_revoke:
            revoke_permissions(
                itgs, user_id, 'No longer a mod',
                passwd_auth_id, perm_ids_to_revoke
            )

    if commit:
        itgs.write_conn.commit()
