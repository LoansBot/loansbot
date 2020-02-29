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
  from ISO 4217 either immediately prior or immediately after the amount,
  separated by a space. Examples: `$10`, `15€`, `RUB 12.50`, `100 JPY`. If no
  currency is indicated then dollars are assumed.
- `<ID>`: The primary identifier for a loan.

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

- `$check <USER>`: The LoansBot responds to the **comment** with information
  pertaining to the **target**. If the **target** has a long history with the
  subreddit, only a summary of that history will be provided. The loansbot
  will include a link to where more information can be found on the **target**.
- `$loan <MONEY>`: The LoansBot stores that the **comment** author
  has lent the **thread** author the **amount**. The **thread** author should
  respond with a confirmation they received the money, but this isn't strictly
  required. The ID of the newly created loan will be included in the
  LoansBot's response.
- `$paid <USER> <MONEY>`: The LoansBot stores that the **comment** author has
  been repaid **amount** by the **target**. If there are multiple loans out
  by the **target** to the **comment** author, the money will be applied to
  the oldest loans first. Any interest will be ignored.
- `$confirm <USER> <MONEY>`: The LoansBot stores that the **comment** author
  has received the **amount** from the **target** as part of a loan.
- `$unpaid <USER>`: The LoansBot marks every loan by the **target** to the
  **comment** author as unpaid. This may cause negative repercussions to the
  **target**.
- `$paid_with_id <ID> <MONEY>`: The LoansBot stores that the given loan has
  been repaid by **amount**. Unlike the standard `$paid` command, this money
  does not automatically get rolled over to other loans if more than the
  original amount is specified.
