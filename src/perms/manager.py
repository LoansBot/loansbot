"""Responsible for determining if a particular user has access to the LoansBot.
"""
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
import time

# The collection we use in ArangoDB for caching user info
COLLECTION = 'perms'


def can_interact(itgs: LazyItgs, username: str, rpiden: str) -> bool:
    """Determines if the user with the given username has permission to
    interact via the LoansBot. Interactions via the LoansBot are not
    privileged and are often subject to review.

    Arguments:
        itgs (LazyItgs): Grants access to networked components
        username (str): The reddit username of the person of interest
        rpiden (str): The identifier to use when using the reddit proxy.
    """
    karma_min = int(os.environ['KARMA_MIN'])
    acc_age_min = float(os.environ['ACCOUNT_AGE_SECONDS_MIN'])

    info = fetch_info(itgs, username, rpiden)
    return (
        not info['borrow_banned']
        and (
            (info['borrow_moderator'] or info['borrow_approved_submitter'])
            or (
                info['karma'] > karma_min
                and time.time() - info['account_created_at'] > acc_age_min
            )
        )
    )


def fetch_info(itgs: LazyItgs, username: str, rpiden: str) -> dict:
    """Get the information we have on the given user. This will attempt to
    fetch it from the cache, but if it is not there or is too old we will
    hit reddit.

    Arguments:
        itgs (LazyItgs): Grants access to networked components
        username (str): The reddit username of the person of interest
        rpiden (str): The identifier to use when using the reddit proxy

    Returns:
        A dict with the following:

        karma (int): How much combined karma the user has
        account_created_at (float): UTC time in seconds the account was created
        borrow_approved_submitter (bool):
            True if they are an approved submitter to /r/borrow, otherwise
            false.
        borrow_moderator (bool):
            True if they are a moderator of /r/borrow, otherwise false
        borrow_banned (bool):
            True if they are banned on /r/borrow, otherwise false
    """
    pass


def flush_cache(itgs: LazyItgs, username: str) -> bool:
    """Deletes any cached information on the given user. This can be invoked
    if the cache was invalidated from, for example, a moderator event.

    Arguments:
        itgs (LazyItgs): Grants access to networked components
        username (str): The reddit username of the person of interest

    Returns:
        True if there was a cache to flush and it was deleted, false otherwise.
    """
    pass
