"""A set of convenience functions for queries."""
import psycopg2


def find_or_create_or_find(itgs, find_query, insert_query):
    """This will execute the find query, returning the result row if there is
    one. Otherwise it will execute the insert query and return the result of
    that if there is no conflict. Finally, if the insert query causes a unique
    constraint error, this will re-attempt the find query.

    This is a useful paradigm for when deletes / modifications of the unique
    constraint rows don't occur and we suspect that selects are more common
    than inserts. So, for example, the currency table will not need many new
    inserts, so a create or find by is very wasteful as it write-locks rows
    unnecessarily. On the other hand a raw find or create is not thread-safe
    and if it were everywhere then the application is very fragile.

    This will not commit.

    Arguments:
        itgs (LazyIntegrations): The lazy integrations to use. This will use
            the write cursor.
        find_query (tuple(str, tuple)): The SQL to execute to find the row. A
            tuple of two arguments, where the first argument is the SQL and the
            second is the parameters if any.
        insert_query (tuple(str, tuple)): The SQL to execute to insert a row;
            should return the inserted id. May raise a unique constraint failure.
            A tuple of two arguments, where the first argument is the SQL and the
            second is the parameters if any.

    Returns:
        (tuple, None): The result from fetchone() after either a succesful find
            or a successful insert
    """
    itgs.write_cursor.execute(*find_query)
    res = itgs.write_cursor.fetchone()
    if res is not None:
        return res
    try:
        itgs.write_cursor.execute(*insert_query)
        return itgs.write_cursor.fetchone()
    except psycopg2.IntegrityError as ex:
        if ex.pgcode != '23505':
            raise

    itgs.write_cursor.execute(*find_query)
    res = itgs.write_cursor.fetchone()
    if res is None:
        raise Exception('find->create->find failed all 3')
    return res
