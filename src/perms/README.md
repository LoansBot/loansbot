# LoansBot Permissions

The website has a sophisticated permissions system for deciding if a user is
allowed to interact or not. On the other hand, for the purpose of the LoansBot,
the only question is whether a user may interact with it or not.

A user is allowed to interact through a comment if the comment is not deleted
by the automoderator and any of the following are true:

- They have at least 1000 combined karma on reddit
- Their reddit account is at least 90 days old
- They are an approved submitter to /r/borrow
- They are a moderator to /r/borrow

Due to how reddit karma has a floor for how much one can lose, it's safe to
assume that combined karma only increases. Since any user under 1000 karma
after 90 days is not particularly attenuated with reddit we may assume it
increases at less than 100 karma/day as long as we give users a way to request
it's rechecked (i.e, for a 0 karma user, we don't  need to recheck their karma
for 10 days to know it's probably not high enough).

All of these questions are very specific to the loansbot permission-related
questions, and we are actually _better_ off if we can make the promise that
this info is only available to loansbot permissions (and the cost only effects
loansbot permissions). This is why none of these questions are visible in the
Postgres schema.

Hence, we want to store a bunch of additional columns on a user (how much karma
does this user have? when did we last check? how old was their account?)
alongside information about the subreddit (who are the approved submitters?
when did they last check? who are the moderators?). This is usually where our
beautiful relational database looks like a mess. It works, it's fast, but it's
confusing and makes the core product look much more complicated.

ArangoDB to the rescue! A simple, fast, disk-based key-value store with TTL
support. We even made a wrapper for it (arango_crud) to make it extremely easy
for this particular use-case.
