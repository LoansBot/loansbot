from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from pypika import PostgreSQLQuery as Query, Table, Parameter
import query_helper


def find_or_create_user(itgs: LazyItgs, unm: str) -> int:
    """Find or create a user with the given username.
    """
    users = Table('users')
    (user_id,) = query_helper.find_or_create_or_find(
        itgs,
        (
            Query.from_(users)
            .select(users.id)
            .where(users.username == Parameter('%s'))
            .get_sql(),
            (unm.lower(),)
        ),
        (
            Query.into(users)
            .columns(users.username)
            .insert(Parameter('%s'))
            .returning(users.id)
            .get_sql(),
            (unm.lower(),)
        )
    )
    return user_id
