# LoansBot

This project contains what most people think of the "LoansBot" as - the scripts
which constantly monitor a list of subreddits for new comments and links and
replies.

## Technical Details

This implementation uses one process for each of the long-running operations
that the LoansBot performs - scanning comments, scanning threads, and marking
pms as read. These use the reddit-proxy service to fairly distribute reddit API
time while remaining comfortably within API limits.

### Parsing

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
- `$loan <MONEY> [AS CURRENCY]`: The LoansBot stores that the **comment** author
  has lent the **thread** author the **amount**. The **thread** author should
  respond with a confirmation they received the money, but this isn't strictly
  required. The ID of the newly created loan will be included in the
  LoansBot's response. The optional `AS <CURRENCY>` (where currency is a
  3-letter ISO 4217 code) is used to indicate the primary currency for the
  transaction is different than what the amount is given in.
  For example `EUR 10 AS USD`. See Currencies for details.
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

### Environment Variables

- `APPNAME`: The application name for logging
- `AMQP_HOST`: The hostname of the amqp service
- `AMQP_VHOST`: The virtual host for the amqp service
- `AMQP_PORT`: The port of the amqp service
- `AMQP_USERNAME`: The username with the amqp service
- `AMQP_PASSWORD`: The password with the amqp service
- `PGHOST`: Host for the database
- `PGPORT`: Port for the database
- `PGDATABASE`: Database name for the database
- `PGUSER`: Username to login as for the database
- `PGPASSWORD`: Password to login with for the database
- `MEMCACHED_HOST`: The hostname for the memcached service
- `MEMCACHED_PORT`: The port for the memcached service
- `AMQP_REDDIT_PROXY_QUEUE`: The name of the queue which the reddit proxy is
- `AMQP_RESPONSE_QUEUE_PREFIX`: A prefix used for response queues by this service
  using within the amqp service.
- `SUBREDDITS`: The subreddits that the loansbot listens to, separated by
  commas
- `KARMA_MIN`: The minimum amount of karma to interact with the loansbot
- `ACCOUNT_AGE_SECONDS_MIN`: The minimum account age in fractional seconds to
  interact with the loansbot
- `CURRENCY_LAYER_API_KEY`: The API access key to communicate with currency
  layer. Must be a paid plan so we can use source currency switching.
- `CURRENCY_LAYER_CACHE_TIME`: How long we cache currency layer results for in
  seconds; defaults to 4 hours.

## Repayments

The LoansBot does not consider interest. A loan is considered repaid when the
entire principal has been repaid, regardless of any outstanding interest. This
is also reflected on the ban status of users (in most circumstances). So a
$100 loan is considered fully repaid when the borrower has returned $100.
Another way of looking at this is that interest amounts are not considered part
of the info relevant to the LoansBot.

## Currencies

Loans can occur in any currency. The amount will be stored in the indicated
currency, which is USD unless otherwise specified, but may be converted to
other currencies as well for statistical purposes. The conversion rates are on
a best-effort basis, which is typically the conversion rate around the time the
command is processed (rather than when the command is made).

To avoid confusion with exchange rates, it is best if the loan is tied to a
particular currency for the purposes of repayment. For example, a loan of 10
U.S. dollars will be considered repaid when 10 U.S. dollars have been repaid.
Similarly, a 10 euro loan is repaid when 10 euro have been repaid.

If a loan is repaid in a different currency than it was provided at, then
exchange rates come into play. A loan has a primary currency, and the repayment
will be converted into the primary currency at the exchange rate when the bot
parses it. So if a $10 loan is given out, and 9 EUR are repaid, the repayment
will be considered complete if at the time of parsing, 9 EUR is worth at least
10 USD.

If the lender and borrower agree that a loan is repaid even though the LoansBot
does not, then the lender may make an additional repayment command for the
missing amount to update the database (even if no actual money exchanges hands
for the second repayment).

Example flows:

### Simple USD

Sending and receiving payments in the same currency is recommended, and the
most common choice is USD.

- Joe lends Sally 10 USD with the command `$loan 10`. The amount is assumed to
  be in USD since no currency was specified. The loan is assumed to be in the
  same currency as the amount.
- Sally repays Joe 10 USD, and Joe indicates this with `$paid /u/Sally 10`. The
  amount is assumed to be in USD since no currency was specified. The amount is
  in the same currency as the loan, so no conversion is required to know the
  loan is repaid.

### Simple EUR

Sending and receiving in the same non-USD currency will also result in easy-to
-understand behavior, and is fully supported.

- Joe lends Sally 10 EUR with the command `$loan 10 EUR`. The amount is given
  in euros explicitly. The loan is assumed to be in the same currency as the
  amount (EUR).
- Sally repays Joe 10 EUR, and Joe indicates this with `$paid /u/Sally 10 EUR`.
  The amount is given in euros explicitly. The amount is in the same currency
  as the loan, so no conversion is required to know the loan is repaid.

### Loan sent in EUR but fixed to USD

If it's known that the repayment will be in a different currency, the safest
choice is for the lender and borrower to agree on an exchange rate in advance,
then transfer the money in the repayment currency (to return to one of the
above examples). Failing that, it's recommended that the loans principal be
specified in the amount it will be returned in, so there is no accidental
repayment under/overflow, as follows:

- Joe lends Sally 10 EUR with the command `$loan 10 EUR AS USD`. The amount is
  interpreted in euros as it was explicitly specified. The loan principal is
  specified to be in USD. To make the example easier to follow, lets say the
  bot converts the 10 EUR into 11 USD. The loan is stored in the database as
  a principal of 11 USD.
- Sally repays Joe 11 USD, and Joe indicates this with `$paid /u/Sally 11`. The
  amount is assumed to be in USD since no currency was specified. The amount is
  in the same currency as the loan, so no conversion is required to know the
  loan is repaid.

### Loan sent in USD but repaid in EUR

Repayments which are in a different currency than the underlying loan can
easily lead to loans which are not marked completely as paid (if the exchange
rate is below what was expected) or have excess applied to other loans (if the
exchange rate is above what was expected). Only advanced users should use this
flow, and even then it is typically better to convert manually then make the
command with the conversion already done

- Joe lends Sally 11 USD with the command `$loan 11`. The amount is assumed to
  be in USD since no currency was specified. The loan is assumed to be in the
  same currency as the amount.
- Sally repays Joe 10 EUR, and Joe indicates this with `$paid /u/Sally 10 EUR`.
  The bot recognizes the loans principal is in dollars, so converts the 10 EUR
  to dollars at the exchange rate when the bot parses. Let's say it converts to
  $11.03. $11 go toward the loan principal and the $0.03 overflows, but there
  are no other loans to apply the $0.03 to so it is ignored.
