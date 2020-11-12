"""This module helps with formatting loans into various formats.
"""
from pydantic import BaseModel
from typing import Optional, List
import pytypeutils as tus
from lbshared.money import Money
from datetime import datetime
from pypika import PostgreSQLQuery as Query, Table, Parameter, Order
from pypika.functions import Count, Sum, Star
from lbshared.lazy_integrations import LazyIntegrations


class Loan(BaseModel):
    """Describes a loan for the purposes of this module, which is already
    joined with all the useful information

    Attributes:
        id (int): The primary key for the loan
        lender (str): The username for the lender
        borrower (str): The username for the borrower
        principal (Money): The amount of money the lender sent the borrower. It
            is preferred if the display settings (symbol/symbol on left) for
            the currency are included.
        principal_repayment (Money): The amount of money the borrower sent the
            lender. It is preferred if the display settings are included.
        permalink (str, None): If a permalink to the comment that produced this
            loan is available, this should be that link. Comes from the loan
            creation info if available and has type 0.
        created_at (datetime): When this loan was made
        repaid_at (datetime, None): When this loan was repaid completely, None
            if that never happened
        unpaid_at (datetime, None): When this loan was marked unpaid, None if
            that never happened or has been undone
    """
    id: int
    lender: str
    borrower: str
    principal: Money
    principal_repayment: Money
    permalink: Optional[str]
    created_at: datetime
    repaid_at: Optional[datetime]
    unpaid_at: Optional[datetime]

    class Config:
        arbitrary_types_allowed = True


def format_loan_table(loans: List[Loan], include_id=False):
    """Format the given list of loans into a markdown table.

    Arguments:
        loans (list[Loan]): The list of loans to format into a table.
        include_id (bool): True if the id of the loan should be included in
            the table, false otherwise

    Returns:
        (str) The markdown formatted table
    """
    tus.check(loans=(loans, (tuple, list)), include_id=(include_id, bool))
    tus.check_listlike(loans=(loans, Loan))

    result_lines = [
        'Lender|Borrower|Amount Given|Amount Repaid|Unpaid?|Original Thread'
        + '|Date Given|Date Paid Back' + ('|id' if include_id else ''),
        ':--|:--|:--|:--|:--|:--|:--|:--' + ('|:--' if include_id else '')
    ]
    line_fmt = '|'.join('{' + a + '}' for a in (
        'lender', 'borrower', 'principal', 'principal_repayment',
        'unpaid_bool', 'permalink', 'created_at_pretty', 'repaid_at_pretty',
        *(['id'] if include_id else [])
    ))
    for loan in loans:
        loan_dict = loan.dict().copy()
        loan_dict['permalink'] = loan_dict.get('permalink', '')
        loan_dict['unpaid_bool'] = '***UNPAID***' if loan.unpaid_at is not None else ''
        loan_dict['created_at_pretty'] = loan.created_at.strftime('%b %d, %Y')
        loan_dict['repaid_at_pretty'] = (
            loan.repaid_at.strftime('%b %d, %Y') if loan.repaid_at is not None else ''
        )
        result_lines.append(line_fmt.format(**loan_dict))

    return '\n'.join(result_lines)


def format_loan_summary(username: str, counts: dict, shown: dict):
    """Formats the summary loan information on the given username. This is a
    format that deliberately omits some loans and splits loans by category.
    It's more verbose for users with very few loans, but much more usable for
    users with many loans.

    Each of the dicts has the following keys:
    - 'paid_as_lender'
    - 'paid_as_borrower'
    - 'unpaid_as_lender'
    - 'unpaid_as_borrower'
    - 'inprogress_as_lender'
    - 'inprogress_as_borrower'

    Arguments:
        username (str): The username of the person we are formatting a loan
            summary for.
        counts (dict): Contains aggregate information by category, which
            doesn't get harder to understand as the number of loans increases.
            Each of the values is a dict with the following keys:

            number_of_loans (int): The number of loans in this category
            principal_of_loans (Money): The sum of the principal of loans in this
                category in the reference USD amount.
        shown (dict): Contains the loans that we want to show in a tabular
            format broken down by category. Each value is a list of loans.
    """
    expected_keys = (
        'paid_as_lender', 'paid_as_borrower', 'unpaid_as_lender', 'unpaid_as_borrower',
        'inprogress_as_lender', 'inprogress_as_borrower'
    )
    tus.check(username=(username, str), counts=(counts, dict), shown=(shown, dict))
    if len(counts) != len(expected_keys):
        raise ValueError(
            f'Expected keys={expected_keys} for counts, '
            + f'but got counts.keys()={tuple(counts.keys())}'
        )
    for key, info in counts.items():
        if key not in expected_keys:
            raise ValueError(
                f'Expected keys={expected_keys} for counts, '
                + f'but got counts.keys()={tuple(counts.keys())}'
            )
        tus.check(**{f'counts_{key}': (info, dict)})
        if len(info) != 2:
            raise ValueError(
                'Expected keys=(number_of_loans, principal_of_loans) for '
                + f'counts_{key}, but got counts[\'{key}\'].keys() = '
                + str(tuple(info.keys()))
            )
        tus.check(**{
            f'counts_{key}_number_of_loans': (info.get('number_of_loans'), int),
            f'counts_{key}_principal_of_loans': (info.get('principal_of_loans'), Money)
        })
    if len(shown) != len(expected_keys):
        raise ValueError(
            f'Expected keys={expected_keys} for shown, '
            + f'but got shown.keys()={tuple(shown.keys())}'
        )
    for key, loans in shown.items():
        if key not in expected_keys:
            raise ValueError(
                f'Expected keys={expected_keys} for shown, '
                + f'but got shown.keys()={tuple(shown.keys())}'
            )
        tus.check(**{f'shown_{key}': (loans, (tuple, list))})
        tus.check_listlike(**{f'shown_{key}': (loans, Loan)})

    result_lines = []

    blocks = (
        (
            'paid_as_borrower',
            '/u/{} has not taken and completely paid back any loans.',
            'Loans paid back with /u/{} as borrower',
            'paid as a borrower'
        ),
        (
            'paid_as_lender',
            '/u/{} has not given out and had completely paid back any loans.',
            'Loans paid back with /u/{} as lender',
            'paid as a lender'
        ),
        (
            'unpaid_as_borrower',
            '/u/{} has not received any loans which are currently marked unpaid',
            'Loans unpaid with /u/{} as borrower',
            'unpaid as a borrower'
        ),
        (
            'unpaid_as_lender',
            '/u/{} has not given any loans which are currently marked unpaid',
            'Loans unpaid with /u/{} as lender',
            'unpaid as a lender'
        ),
        (
            'inprogress_as_borrower',
            '/u/{} does not have any outstanding loans as a borrower',
            'In-progress loans with /u/{} as borrower',
            'inprogress as a borrower'
        ),
        (
            'inprogress_as_lender',
            '/u/{} does not have any outstanding loans as a lender',
            'In-progress loans with /u/{} as lender',
            'inprogress as a lender'
        )
    )
    for key, empty_fmt, table_title_fmt, adjective in blocks:
        if counts[key]['number_of_loans'] == 0:
            result_lines.append(empty_fmt.format(username))
        elif shown[key]:
            num_missing = counts[key]['number_of_loans'] - len(shown[key])
            extra = ''
            if num_missing > 0:
                extra = ' (**{} loan{} omitted from the table**)'.format(
                    num_missing,
                    's' if num_missing != 1 else ''
                )

            result_lines.append(
                '{} ({} loan{}, {}){}:'.format(
                    table_title_fmt.format(username),
                    counts[key]['number_of_loans'],
                    's' if counts[key]['number_of_loans'] != 1 else '',
                    counts[key]['principal_of_loans'],
                    extra
                )
            )
            result_lines.append(format_loan_table(shown[key]))
        else:
            result_lines.append(
                '/u/{} has {} loan{} {}, for a total of {}'.format(
                    username,
                    counts[key]['number_of_loans'],
                    's' if counts[key]['number_of_loans'] != 1 else '',
                    adjective,
                    counts[key]['principal_of_loans']
                )
            )

    return '\n\n'.join(result_lines)


def get_all_loans(itgs: LazyIntegrations, username: str):
    """Gets the list of all loans for the given username.

    Example:
        print(format_loan_table(get_all_loans(itgs, username)))

    Arguments:
        username (str): The username of the user to get the loans involving.
            A loan involves a user if they are the lender or the borrower.

    Returns:
        loans (List[Loan]): All the loans involving the user with the given
            username.
    """
    loans = Table('loans')
    lenders = Table('lenders')
    borrowers = Table('borrowers')

    itgs.read_cursor.execute(
        create_loans_query()
        .where(
            (lenders.username == Parameter('%s'))
            | (borrowers.username == Parameter('%s'))
        )
        .orderby(loans.created_at, order=Order.desc)
        .get_sql(),
        (username.lower(), username.lower())
    )
    result = []

    row = itgs.read_cursor.fetchone()
    while row is not None:
        result.append(fetch_loan(row))
        row = itgs.read_cursor.fetchone()

    return result


def get_summary_info(itgs: LazyIntegrations, username: str, max_loans_per_table: int = 7):
    """Get all of the information for a loan summary for the given username in
    a reasonably performant way.

    Example:
        print(format_loan_summary(*get_summary_info(itgs, username)))

    Arguments:
        itgs (LazyIntegrations): The integrations to use
        username (str): The username to fetch summary information for.
        max_loans_per_table (int): For the sections which we prefer to expand
            the loans for, this is the maximum number of loans we're willing to
            include in the table. If this is too large the table can become
            very difficult to read on some mobile clients, and if this is way
            too large we risk hitting the 5000 character limit.

    Returns:
        (str, dict, dict) The username, counts, and shown as described as the
        arguments to format_loan_summary
    """
    loans = Table('loans')
    moneys = Table('moneys')
    principals = moneys.as_('principals')
    users = Table('users')
    lenders = users.as_('lenders')
    borrowers = users.as_('borrowers')

    now = datetime.utcnow()
    oldest_loans_in_table = datetime(now.year - 1, now.month, now.day)

    counts = {}
    shown = {}

    itgs.read_cursor.execute(
        Query.from_(loans)
        .select(Count(Star()), Sum(principals.amount_usd_cents))
        .join(lenders).on(lenders.id == loans.lender_id)
        .join(principals).on(principals.id == loans.principal_id)
        .where(lenders.username == Parameter('%s'))
        .where(loans.repaid_at.notnull())
        .where(loans.deleted_at.isnull())
        .get_sql(),
        (username.lower(),)
    )
    (num_loans, princ_loans) = itgs.read_cursor.fetchone()
    counts['paid_as_lender'] = {'number_of_loans': num_loans, 'principal_of_loans': princ_loans}
    shown['paid_as_lender'] = []

    itgs.read_cursor.execute(
        Query.from_(loans)
        .select(Count(Star()), Sum(principals.amount_usd_cents))
        .join(borrowers).on(borrowers.id == loans.borrower_id)
        .join(principals).on(principals.id == loans.principal_id)
        .where(borrowers.username == Parameter('%s'))
        .where(loans.repaid_at.notnull())
        .where(loans.deleted_at.isnull())
        .get_sql(),
        (username.lower(),)
    )
    (num_loans, princ_loans) = itgs.read_cursor.fetchone()
    counts['paid_as_borrower'] = {
        'number_of_loans': num_loans,
        'principal_of_loans': princ_loans
    }
    shown['paid_as_borrower'] = []

    itgs.read_cursor.execute(
        Query.from_(loans)
        .select(Count(Star()), Sum(principals.amount_usd_cents))
        .join(lenders).on(lenders.id == loans.lender_id)
        .join(principals).on(principals.id == loans.principal_id)
        .where(lenders.username == Parameter('%s'))
        .where(loans.unpaid_at.notnull())
        .where(loans.deleted_at.isnull())
        .get_sql(),
        (username.lower(),)
    )
    (num_loans, princ_loans) = itgs.read_cursor.fetchone()
    counts['unpaid_as_lender'] = {
        'number_of_loans': num_loans,
        'principal_of_loans': princ_loans
    }
    shown['unpaid_as_lender'] = []

    if num_loans > 0:
        itgs.read_cursor.execute(
            create_loans_query()
            .where(lenders.username == Parameter('%s'))
            .where(loans.unpaid_at.notnull())
            .where(loans.created_at > Parameter('%s'))
            .orderby(loans.created_at, order=Order.desc)
            .limit(max_loans_per_table)
            .get_sql(),
            (username.lower(), oldest_loans_in_table)
        )
        row = itgs.read_cursor.fetchone()
        while row is not None:
            shown['unpaid_as_lender'].append(fetch_loan(row))
            row = itgs.read_cursor.fetchone()

    itgs.read_cursor.execute(
        Query.from_(loans)
        .select(Count(Star()), Sum(principals.amount_usd_cents))
        .join(borrowers).on(borrowers.id == loans.borrower_id)
        .join(principals).on(principals.id == loans.principal_id)
        .where(borrowers.username == Parameter('%s'))
        .where(loans.unpaid_at.notnull())
        .where(loans.deleted_at.isnull())
        .get_sql(),
        (username.lower(),)
    )
    (num_loans, princ_loans) = itgs.read_cursor.fetchone()
    counts['unpaid_as_borrower'] = {
        'number_of_loans': num_loans,
        'principal_of_loans': princ_loans
    }
    shown['unpaid_as_borrower'] = []

    if num_loans > 0:
        itgs.read_cursor.execute(
            create_loans_query()
            .where(borrowers.username == Parameter('%s'))
            .where(loans.unpaid_at.notnull())
            .where(loans.created_at > Parameter('%s'))
            .orderby(loans.created_at, order=Order.desc)
            .limit(max_loans_per_table)
            .get_sql(),
            (username.lower(), oldest_loans_in_table)
        )
        row = itgs.read_cursor.fetchone()
        while row is not None:
            shown['unpaid_as_borrower'].append(fetch_loan(row))
            row = itgs.read_cursor.fetchone()

    itgs.read_cursor.execute(
        Query.from_(loans)
        .select(Count(Star()), Sum(principals.amount_usd_cents))
        .join(lenders).on(lenders.id == loans.lender_id)
        .join(principals).on(principals.id == loans.principal_id)
        .where(lenders.username == Parameter('%s'))
        .where(loans.unpaid_at.isnull())
        .where(loans.repaid_at.isnull())
        .where(loans.deleted_at.isnull())
        .get_sql(),
        (username.lower(),)
    )
    (num_loans, princ_loans) = itgs.read_cursor.fetchone()
    counts['inprogress_as_lender'] = {
        'number_of_loans': num_loans,
        'principal_of_loans': princ_loans
    }
    shown['inprogress_as_lender'] = []

    if num_loans > 0:
        itgs.read_cursor.execute(
            create_loans_query()
            .where(lenders.username == Parameter('%s'))
            .where(loans.unpaid_at.isnull())
            .where(loans.repaid_at.isnull())
            .where(loans.created_at > Parameter('%s'))
            .orderby(loans.created_at, order=Order.desc)
            .limit(max_loans_per_table)
            .get_sql(),
            (username.lower(), oldest_loans_in_table)
        )
        row = itgs.read_cursor.fetchone()
        while row is not None:
            shown['inprogress_as_lender'].append(fetch_loan(row))
            row = itgs.read_cursor.fetchone()

    itgs.read_cursor.execute(
        Query.from_(loans)
        .select(Count(Star()), Sum(principals.amount_usd_cents))
        .join(borrowers).on(borrowers.id == loans.borrower_id)
        .join(principals).on(principals.id == loans.principal_id)
        .where(borrowers.username == Parameter('%s'))
        .where(loans.unpaid_at.isnull())
        .where(loans.repaid_at.isnull())
        .where(loans.deleted_at.isnull())
        .get_sql(),
        (username.lower(),)
    )
    (num_loans, princ_loans) = itgs.read_cursor.fetchone()
    counts['inprogress_as_borrower'] = {
        'number_of_loans': num_loans,
        'principal_of_loans': princ_loans
    }
    shown['inprogress_as_borrower'] = []

    if num_loans > 0:
        itgs.read_cursor.execute(
            create_loans_query()
            .where(borrowers.username == Parameter('%s'))
            .where(loans.unpaid_at.isnull())
            .where(loans.repaid_at.isnull())
            .where(loans.created_at > Parameter('%s'))
            .orderby(loans.created_at, order=Order.desc)
            .limit(max_loans_per_table)
            .get_sql(),
            (username.lower(), oldest_loans_in_table)
        )
        row = itgs.read_cursor.fetchone()
        while row is not None:
            shown['inprogress_as_borrower'].append(fetch_loan(row))
            row = itgs.read_cursor.fetchone()

    for cnt in counts.values():
        princ = cnt['principal_of_loans']
        if princ is None:
            princ = 0

        cnt['principal_of_loans'] = Money(
            princ, 'USD',
            exp=2, symbol='$', symbol_on_left=True
        )

    return (username, counts, shown)


def get_and_format_all_or_summary(itgs: LazyIntegrations, username: str, threshold: int = 5):
    """Checks how many loans the given user has. If it's at or above the
    threshold, this fetches the summary info on the user and formats it,
    then returns the formatted summary. If it's below the threshold,
    fetches all the loans for that user, formats it into a table, and returns
    the formatted table.

    Arguments:
        itgs (LazyIntegrations): The integrations to use for getting info
        username (str): The username to check
        threshold (int): The number of loans required for a summary instead of
            just all the loans in a table

    Returns:
        (str): A markdown representation of the users loans
    """
    loans = Table('loans')
    users = Table('users')
    lenders = users.as_('lenders')
    borrowers = users.as_('borrowers')

    itgs.read_cursor.execute(
        Query.from_(loans).select(Count(Star()))
        .join(lenders).on(lenders.id == loans.lender_id)
        .join(borrowers).on(borrowers.id == loans.borrower_id)
        .where(
            (lenders.username == Parameter('%s'))
            | (borrowers.username == Parameter('%s'))
        )
        .where(loans.deleted_at.isnull())
        .get_sql(),
        (username.lower(), username.lower())
    )
    (cnt,) = itgs.read_cursor.fetchone()
    if cnt < threshold:
        return format_loan_table(get_all_loans(itgs, username))
    return format_loan_summary(*get_summary_info(itgs, username))


def create_loans_query():
    """Create a query which will convert every loan into a single row which can
    be converted to a Loan object using fetch_loan.

    Returns:
        (Query): A query object which is unordered and not limited with no
            restriction on which loans are included (except excluding deleted),
            but will return one row per loan which can be interpreted with
            fetch_loan.
    """
    loans = Table('loans')
    users = Table('users')
    moneys = Table('moneys')
    currencies = Table('currencies')
    loan_creation_infos = Table('loan_creation_infos')

    lenders = users.as_('lenders')
    borrowers = users.as_('borrowers')
    principals = moneys.as_('principals')
    principal_currencies = currencies.as_('principal_currencies')
    principal_repayments = moneys.as_('principal_repayments')
    principal_repayment_currencies = currencies.as_('principal_repayment_currencies')

    return (
        Query.from_(loans)
        .select(
            loans.id,
            lenders.username,
            borrowers.username,
            principals.amount,
            principal_currencies.code,
            principal_currencies.symbol,
            principal_currencies.symbol_on_left,
            principal_currencies.exponent,
            principal_repayments.amount,
            principal_repayment_currencies.code,
            principal_repayment_currencies.symbol,
            principal_repayment_currencies.symbol_on_left,
            principal_repayment_currencies.exponent,
            loan_creation_infos.type,
            loan_creation_infos.parent_fullname,
            loan_creation_infos.comment_fullname,
            loans.created_at,
            loans.repaid_at,
            loans.unpaid_at
        )
        .join(lenders).on(lenders.id == loans.lender_id)
        .join(borrowers).on(borrowers.id == loans.borrower_id)
        .join(principals).on(principals.id == loans.principal_id)
        .join(principal_currencies).on(principal_currencies.id == principals.currency_id)
        .join(principal_repayments).on(principal_repayments.id == loans.principal_repayment_id)
        .join(principal_repayment_currencies)
        .on(principal_repayment_currencies.id == principal_repayments.currency_id)
        .left_join(loan_creation_infos).on(loan_creation_infos.loan_id == loans.id)
        .where(loans.deleted_at.isnull())
    )


def fetch_loan(row):
    """Converts a row result from create_loans_query into a Loan object.

    Arguments:
        row (tuple): The row returned from postgres

    Returns:
        (Loan) The loan object
    """
    (
        loan_id,
        lender_username,
        borrower_username,
        principal_amount,
        principal_code,
        principal_symbol,
        principal_symbol_on_left,
        principal_exp,
        principal_repayment_amount,
        principal_repayment_code,
        principal_repayment_symbol,
        principal_repayment_symbol_on_left,
        principal_repayment_exp,
        creation_type,
        creation_parent_fullname,
        creation_comment_fullname,
        created_at,
        repaid_at,
        unpaid_at
    ) = row

    permalink = None
    if creation_type == 0:
        permalink = 'https://www.reddit.com/comments/{}/redditloans/{}'.format(
            creation_parent_fullname[3:],
            creation_comment_fullname[3:]
        )

    return Loan(
        id=loan_id,
        lender=lender_username,
        borrower=borrower_username,
        principal=Money(
            principal_amount, principal_code,
            exp=principal_exp, symbol=principal_symbol,
            symbol_on_left=principal_symbol_on_left
        ),
        principal_repayment=Money(
            principal_repayment_amount, principal_repayment_code,
            exp=principal_repayment_exp, symbol=principal_repayment_symbol,
            symbol_on_left=principal_symbol_on_left
        ),
        permalink=permalink,
        created_at=created_at,
        repaid_at=repaid_at,
        unpaid_at=unpaid_at
    )
