"""Utility functions for granting and revoking permissions"""
from pypika import PostgreSQLQuery as Query, Table, Parameter
import typing

if typing.TYPE_CHECKING:
    from lbshared.lazy_integrations import LazyIntegrations as LazyItgs


def grant_permissions(
        itgs: 'LazyItgs', user_id: int, reason: str, passwd_auth_id: int,
        perm_ids_to_grant: list, commit=False):
    """Grants all of the given permissions to the given user. The permissions
    to grant must not already be on the user. You must provide the password
    authentication id to grant the permissions to. This will record the event
    in the audit table.

    Arguments:
    - `itgs (LazyItgs)`: The integrations to connect to networked services on
    - `user_id (int)`: The user the password authentication id belongs to
    - `passwd_auth_id (int)`: The password authentication to grant the
      permissions to.
    - `perm_ids_to_grant (list[int])`: The ids of the permissions to grant.
      Must not be empty.
    - `commit (bool)`: True to commit the transaction immediately, false not
      to.
    """
    passwd_auth_perms = Table('password_auth_permissions')
    itgs.write_cursor.execute(
        Query.into(passwd_auth_perms)
        .columns(
            passwd_auth_perms.password_authentication_id,
            passwd_auth_perms.permission_id
        )
        .insert(
            *((Parameter('%s'), Parameter('%s')) for _ in perm_ids_to_grant)
        )
        .get_sql(),
        tuple(
            (passwd_auth_id, perm_id)
            for perm_id in perm_ids_to_grant
        )
    )
    passwd_auth_events = Table('password_authentication_events')
    itgs.write_cursor.execute(
        Query.into(passwd_auth_events)
        .columns(
            passwd_auth_events.password_authentication_id,
            passwd_auth_events.type,
            passwd_auth_events.reason,
            passwd_auth_events.user_id,
            passwd_auth_events.permission_id
        )
        .insert(
            *(
                (passwd_auth_id, 'permission-granted', reason, user_id, perm_id)
                for perm_id in perm_ids_to_grant
            )
        )
    )
    if commit:
        itgs.write_conn.commit()


def revoke_permissions(
        itgs: 'LazyItgs', user_id: int, reason: str, passwd_auth_id: int,
        perm_ids_to_revoke: list, commit=False):
    """Revokes all the given permissions from the given password authentication
    id. The password authentication must have all of the permissions. This will
    record the event in the audit table. This will log the user out.

    Arguments:
    - `itgs (LazyItgs)`: The integrations to connect to third part services on
    - `user_id (int)`: The user the password authentication belong sto.
    - `reason (str)`: The reason for revoking permissions
    - `passwd_auth_id (int)`: The password authentication to revoke permissions
      on.
    - `perm_ids_to_revoke (list[int])`: The ids of the permissions to revoke
    - `commit (bool)`: True to commit the transaction immediately, false not
      to.
    """
    passwd_auth_perms = Table('password_auth_permissions')
    itgs.write_cursor.execute(
        Query.from_(passwd_auth_perms).delete()
        .where(passwd_auth_perms.password_authentication_id == Parameter('%s'))
        .where(passwd_auth_perms.permission_id.isin(*(Parameter('%s') for _ in perm_ids_to_revoke)))
        .get_sql(),
        (passwd_auth_id, *perm_ids_to_revoke)
    )
    passwd_auth_events = Table('password_authentication_events')
    itgs.write_cursor.execute(
        Query.into(passwd_auth_events)
        .columns(
            passwd_auth_events.password_authentication_id,
            passwd_auth_events.type,
            passwd_auth_events.reason,
            passwd_auth_events.user_id,
            passwd_auth_events.permission_id
        )
        .insert(
            *(
                (passwd_auth_id, 'permission-revoked', reason, user_id, perm_id)
                for perm_id in perm_ids_to_revoke
            )
        )
    )
    authtokens = Table('authtokens')
    itgs.write_cursor.execute(
        Query.from_(authtokens)
        .delete()
        .where(authtokens.user_id == Parameter('%s'))
        .get_sql(),
        (user_id,)
    )
    if commit:
        itgs.write_conn.commit()
