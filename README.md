# LoansBot

This project contains what most people think of the "LoansBot" as - the scripts
which constantly monitor a list of subreddits for new comments and links and
replies.

## Technical Details

This implementation uses one process for each of the long-running operations
that the LoansBot performs - scanning comments, scanning threads, and marking
pms as read. These use the reddit-proxy service to fairly distribute reddit API
time while remaining comfortably within API limits.

Since the LoansBot uses reddit as the storage for how commands are posted,
there are a number of related oddities in the parsing structure. To simplify
the explanation of what each command is, the following explains various
components of commands:

- `<USER>`: A user link is either a username prefixed with `/u/` or `u/`, such
  as `/u/Tjstretchalot`, or a link to a users profile where the visible text
  for the link is as before. For example:
  `[u/Tjstretchalot](https://www.reddit.com/user/Tjstretchalot)`. The link may
  use either the long-form `/user/` syntax or the shortform `/u/` syntax.
- `<MONEY>`: Money is specified in fractional units. It may be prefixed or
  suffixed with any common utf-8 currency symbols: $, £, € to indicate the
  currency. Alternatively, it can involve any common 3 letter currency code
  either immediately prior or immediately after the amount, separated by
  a space. Examples: `$10`, `15€`, `RUB 12.50`, `100 JPY`. If no currency is
  indicated then dollars are assumed.
- `<DATETIME>`: As described in ISO 8601. Example: `2020-02-28T13:10:14+00:00`.

### Comment Commands

Terminology:

When bolded, words are following exactly to the following definitions:

- The term **comment** corresponds to the comment containing the command.
- The term **thread** corresponds to the thread containing the comment
  containing the command
- The term **target** will be used to identify the user specified within
  the command.
- The term **amount** will be used to identify the monetary amount specified
  within the command.

Supported commands:

- `$check <USER>`: The loansbot responds to the **comment** with information
  pertaining to the **target**. If the **target** has a long history with the
  subreddit, only a summary of that history will be provided. The loansbot
  will include a link to where more information can be found on the **target**.
- `$loan <MONEY>`:

## Link Commands
