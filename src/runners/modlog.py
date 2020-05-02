"""This is the entry point of a process which scans the borrow moderator queue
to speed up propagation of moderator events to our caches.

If a user is promoted to moderator, demoted from moderator, approved,
unapproved, banned, or unbanned we flush their permissions cache.
"""
# from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
