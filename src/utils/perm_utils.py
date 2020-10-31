"""Utility functions for granting and revoking permissions"""
from pypika import PostgreSQLQuery as Query, Table, Parameter
import query_helper
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

    args = []
    for perm_id in perm_ids_to_grant:
        args.append(passwd_auth_id)
        args.append(perm_id)

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
        args
    )
    passwd_auth_events = Table('password_authentication_events')

    loansbot_user_id = get_loansbot_user_id(itgs)
    args = []
    for perm_id in perm_ids_to_grant:
        args.append(passwd_auth_id)
        args.append('permission-granted')
        args.append(reason)
        args.append(loansbot_user_id)
        args.append(perm_id)

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
                tuple(Parameter('%s') for _ in range(5))
                for _ in perm_ids_to_grant
            )
        )
        .get_sql(),
        args
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
    loansbot_user_id = get_loansbot_user_id(itgs)
    args = []
    for perm_id in perm_ids_to_revoke:
        args.append(passwd_auth_id)
        args.append('permission-revoked')
        args.append(reason)
        args.append(loansbot_user_id)
        args.append(perm_id)

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
                tuple(Parameter('%s') for _ in range(5))
                for _ in perm_ids_to_revoke
            )
        )
        .get_sql(),
        args
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


def get_loansbot_user_id(itgs: 'LazyItgs') -> int:
    """This function returns the id of the loansbot user. If they do not exist
    they are created. This is useful since thats the "author" of automated
    permission changes.

    Arguments:
    - `itgs (LazyItgs)`: The integrations for connecting to networked
        services.

    Returns:
    - `loansbot_user_id (int)`: The id of the loansbot user.
    """
    users = Table('users')
    unm = 'loansbot'
    (user_id,) = query_helper.find_or_create_or_find(
        itgs,
        (
            Query.from_(users)
            .select(users.id)
            .where(users.username == Parameter('%s'))
            .get_sql(),
            (unm,)
        ),
        (
            Query.into(users)
            .columns(users.username)
            .insert(Parameter('%s'))
            .returning(users.id)
            .get_sql(),
            (unm,)
        )
    )
    return user_id
