"""Responsible for determining if a particular user has access to the LoansBot.
"""
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
import utils.reddit_proxy
import time
import os


COLLECTION = "perms"
"""The collection we use in ArangoDB for caching user info"""

COMBINED_KARMA_MIN = int(os.environ["KARMA_MIN"])
"""The minimum amount of karma to interact with this subreddit"""

COMMENT_KARMA_MIN = (
    int(os.environ["COMMENT_KARMA_MIN"])
    if "COMMENT_KARMA_MIN" in os.environ
    else int(0.4 * COMBINED_KARMA_MIN)
)
"""The minimum amount of comment karma to interact with this subreddit"""

ACCOUNT_AGE_SECONDS_MIN = float(os.environ["ACCOUNT_AGE_SECONDS_MIN"])
"""The minimum account age to interact"""

IGNORED_USERS = frozenset(
    s.lower() for s in os.environ.get("IGNORED_USERS", "LoansBot").split(",")
)
"""The users we don't allow to interact, perhaps because they are us!"""


def can_interact(itgs: LazyItgs, username: str, rpiden: str, rpversion: float) -> bool:
    """Determines if the user with the given username has permission to
    interact via the LoansBot. Interactions via the LoansBot are not
    privileged and are often subject to review.

    Arguments:
        itgs (LazyItgs): Grants access to networked components
        username (str): The reddit username of the person of interest
        rpiden (str): The identifier to use when using the reddit proxy.
        rpversion (float): The versino number to use when using the reddit proxy
    """
    if username.lower() in IGNORED_USERS:
        return False
    info = fetch_info(itgs, username, rpiden, rpversion)
    if info is None:
        return False
    return not info["borrow_banned"] and (
        (info["borrow_moderator"] or info["borrow_approved_submitter"])
        or (
            info["karma"] > COMBINED_KARMA_MIN
            and info["comment_karma"] > COMMENT_KARMA_MIN
            and time.time() - info["account_created_at"] > ACCOUNT_AGE_SECONDS_MIN
        )
    )


def fetch_info(itgs: LazyItgs, username: str, rpiden: str, rpversion: float) -> dict:
    """Get the information we have on the given user. This will attempt to
    fetch it from the cache, but if it is not there or is too old we will
    hit reddit.

    Arguments:
        itgs (LazyItgs): Grants access to networked components
        username (str): The reddit username of the person of interest
        rpiden (str): The identifier to use when using the reddit proxy
        rpversion (float): The version number to use when using the reddit proxy

    Returns:
        None if the account does not exist, othewise a dict with the following:

        karma (int): How much combined karma the user has
        comment_karma (int): How much comment karma the user has
        account_created_at (float): UTC time in seconds the account was created
        borrow_approved_submitter (bool):
            True if they are an approved submitter to /r/borrow, otherwise
            false.
        borrow_moderator (bool):
            True if they are a moderator of /r/borrow, otherwise false
        borrow_banned (bool):
            True if they are banned on /r/borrow, otherwise false
    """
    doc = itgs.kvs_db.collection(COLLECTION).document(username.lower())
    cache_hit = doc.read()

    if cache_hit and "comment_karma" not in doc.body:
        # Old schema
        cache_hit = False

    if (
        cache_hit
        and (time.time() - doc.body["checked_karma_at"]) > 60 * 60 * 24
        and doc.body["karma"] < COMBINED_KARMA_MIN
        and (
            doc.body["karma"]
            + (time.time() - doc.body["checked_karma_at"]) * 100 / (60 * 60 * 24)
            >= COMBINED_KARMA_MIN
        )
    ):
        # If they earned 100 karma/day they would have enough karma by now
        cache_hit = False

    if not cache_hit:
        karma_and_age = utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, "show_user", {"username": username}
        )
        if karma_and_age["type"] != "copy":
            return None
        is_moderator = utils.reddit_proxy.send_request(
            itgs,
            rpiden,
            rpversion,
            "user_is_moderator",
            {"subreddit": "borrow", "username": username},
        )
        is_approved = utils.reddit_proxy.send_request(
            itgs,
            rpiden,
            rpversion,
            "user_is_approved",
            {"subreddit": "borrow", "username": username},
        )
        is_banned = utils.reddit_proxy.send_request(
            itgs,
            rpiden,
            rpversion,
            "user_is_banned",
            {"subreddit": "borrow", "username": username},
        )
        doc.body = {
            "karma": karma_and_age["info"]["cumulative_karma"],
            "comment_karma": karma_and_age["info"]["comment_karma"],
            "link_karma": karma_and_age["info"]["link_karma"],
            "account_created_at": karma_and_age["info"]["created_at_utc_seconds"],
            "borrow_approved_submitter": is_approved["info"]["approved"],
            "borrow_moderator": is_moderator["info"]["moderator"],
            "borrow_banned": is_banned["info"]["banned"],
            "checked_karma_at": time.time(),
        }
        doc.create_or_overwrite(ttl=60 * 60 * 24 * 365)

    return doc.body


def flush_cache(itgs: LazyItgs, username: str) -> bool:
    """Deletes any cached information on the given user. This can be invoked
    if the cache was invalidated from, for example, a moderator event.

    Arguments:
        itgs (LazyItgs): Grants access to networked components
        username (str): The reddit username of the person of interest

    Returns:
        True if there was a cache to flush and it was deleted, false otherwise.
    """
    return itgs.kvs_db.collection(COLLECTION).force_delete_doc(username)
