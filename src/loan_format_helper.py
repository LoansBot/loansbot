"""This module helps with formatting loans into various formats.
"""
from pydantic import BaseModel
from typing import Optional, List
import pytypeutils as tus
from money import Money
from datetime import datetime, timezone


class Loan(BaseModel):
    """Describes a loan for the purposes of this module, which is already
    joined with all the useful information

    Attributes:
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


def format_loan_table(loans: List[Loan]):
    """Format the given list of loans into a markdown table.
    """
    tus.check(loans=(loans, (tuple, list)))
    tus.check_listlike(loans=(loans, Loan))

    result_lines = [
        'Lender|Borrower|Amount Given|Amount Repaid|Unpaid?|Original Thread|Date Given|Date Paid Back',
        ':--|:--|:--|:--|:--|:--|:--|:--'
    ]
    line_fmt = '|'.join('{' + a + '}' for a in (
        'lender', 'borrower', 'principal', 'principal_repayment',
        'unpaid_bool', 'permalink', 'created_at_pretty', 'repaid_at_pretty'
    ))
    for loan in loans:
        loan_dict = loan.dict().copy()
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

    result_lines = [
        '/u/{} has taken out and paid back {} loan{}, for a total of {}'.format(
            username,
            counts['paid_as_borrower']['number_of_loans'],
            's' if counts['paid_as_borrower']['number_of_loans'] != 1 else '',
            counts['paid_as_borrower']['principal_of_loans']
        ),
        '/u/{} has given out and gotten returned {} loan{}, for a total of {}'.format(
            username,
            counts['paid_as_lender']['number_of_loans'],
            's' if counts['paid_as_lender']['number_of_loans'] != 1 else '',
            counts['paid_as_lender']['principal_of_loans']
        )
    ]

    blocks = (
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
                '/u/{} has **{} loan{} {}**, for a total of {}'.format(
                    username,
                    counts[key]['number_of_loans'],
                    's' if counts[key]['number_of_loans'] != 1 else '',
                    adjective,
                    counts[key]['principal_of_loans']
                )
            )

    return '\n\n'.join(result_lines)
