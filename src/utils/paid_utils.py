"""This file provides utility functions related to paid summons"""
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Now
from money import Money
from convert import convert
import pytypeutils as tus
import math


def apply_repayment(itgs: LazyItgs, loan_id: int, amount: Money):
    """Applies up to the given amount of money to the given loan. This will
    convert the amount to the loans currency if necessary. This will return the
    primary key of the loan_repayment_events row that was created, the amount
    of money that was applied to the loan (which will be in the loan currency),
    and the amount of money which exceeded the remaining principal to be repaid
    on this loan (which will be in the provided currency).

    This does not commit anything and expects to be running with explicit
    commits, i.e., where this is running in a transaction which it does not
    itself commit.

    For consistency this will use the same conversion rate to USD for the loan
    as when the loan was initially created.

    Example:
        (repayment_event_id, amount_applied, amount_remaining) = apply_repayment(
            itgs, loan_id, amount
        )

    Raises:
        ValueError: If the loan does not exist, is already repaid or, the
          amount is 0.

    Arguments:
        itgs (LazyIntegrations): The lazy loaded networked services connector
        loan_id (int): The primary key of the loan to apply the repayment to
        amount (Money): The amount of money to apply toward this loan. This may
            be in any currency, although it will be converted to the loans
            currency.

    Returns:
        repayment_event_id (int): The primary key of of the loan repayment
            event that this created.
        amount_applied (Money): The amount of money that was applied toward
            the loan, in the loans currency.
        amount_remaining (Money): The amount of money that is remaining, in
            the same currency that the amount was given in.
    """
    tus.check(
        itgs=(itgs, LazyItgs),
        loan_id=(loan_id, int),
        amount=(amount, Money)
    )
    if amount.minor <= 0:
        raise ValueError(
            f'Cannot apply {amount} toward a loan (only positive amounts can be applied)'
        )

    loans = Table('loans')
    moneys = Table('moneys')
    principals = moneys.as_('principals')
    principal_repayments = moneys.as_('principal_repayments')
    currencies = Table('currencies')
    principal_currencies = currencies.as_('principal_currencies')

    itgs.write_cursor.execute(
        Query.from_(loans)
        .select(
            principal_currencies.id,
            principal_currencies.code,
            principal_currencies.exponent,
            principal_currencies.symbol,
            principal_currencies.symbol_on_left,
            principals.amount,
            principals.amount_usd_cents,
            principal_repayments.id,
            principal_repayments.amount,
            loans.unpaid_at
        )
        .join(principals).on(principals.id == loans.principal_id)
        .join(principal_currencies).on(principal_currencies.id == principals.currency_id)
        .join(principal_repayments).on(principal_repayments.id == loans.principal_repayment_id)
        .where(loans.id == Parameter('%s'))
        .get_sql(),
        (loan_id,)
    )
    row = itgs.write_cursor.fetchone()
    if row is None:
        raise ValueError(f'Loan {loan_id} does not exist')

    (
        loan_currency_id,
        loan_currency,
        loan_currency_exp,
        loan_currency_symbol,
        loan_currency_symbol_on_left,
        principal_amount,
        principal_usd_cents,
        principal_repayment_id,
        principal_repayment_amount,
        unpaid_at
    ) = row

    rate_loan_to_usd = (principal_amount / float(principal_usd_cents))

    if principal_amount == principal_repayment_amount:
        raise ValueError(f'Loan {loan_id} is already repaid')

    if loan_currency == amount.currency:
        loan_currency_amount = amount
    else:
        rate_given_to_loan = convert(itgs, amount.currency, loan_currency)
        loan_currency_amount = Money(
            int(math.ceil(amount.minor * rate_given_to_loan)),
            loan_currency, exp=loan_currency_exp, symbol=loan_currency_symbol,
            symbol_on_left=loan_currency_symbol_on_left
        )

    applied = Money(
        min(principal_amount - principal_repayment_amount, loan_currency_amount.minor),
        loan_currency,
        exp=loan_currency_exp,
        symbol=loan_currency_symbol,
        symbol_on_left=loan_currency_symbol_on_left
    )
    applied_usd_cents = int(math.ceil(applied.minor / rate_loan_to_usd))

    if loan_currency == amount.currency:
        remaining = Money(
            amount.minor - applied.minor,
            loan_currency, exp=loan_currency_exp, symbol=loan_currency_symbol,
            symbol_on_left=loan_currency_symbol_on_left
        )
    else:
        applied_in_given_currency = int(math.ceil(applied.minor / rate_given_to_loan))
        remaining = Money(
            max(0, amount.minor - applied_in_given_currency),
            amount.currency, exp=amount.exp, symbol=amount.symbol,
            symbol_on_left=amount.symbol_on_left
        )

    itgs.write_cursor.execute(
        Query.into(moneys)
        .columns(
            moneys.currency_id,
            moneys.amount,
            moneys.amount_usd_cents
        )
        .insert(*[Parameter('%s') for _ in range(3)])
        .returning(moneys.id)
        .get_sql(),
        (
            loan_currency_id,
            applied.minor,
            applied_usd_cents
        )
    )
    (repayment_event_money_id,) = itgs.write_cursor.fetchone()

    loan_repayment_events = Table('loan_repayment_events')
    itgs.write_cursor.execute(
        Query.into(loan_repayment_events)
        .columns(
            loan_repayment_events.loan_id,
            loan_repayment_events.repayment_id
        )
        .insert(*[Parameter('%s') for _ in range(2)])
        .returning(loan_repayment_events.id)
        .get_sql(),
        (
            loan_id,
            repayment_event_money_id
        )
    )
    (repayment_event_id,) = itgs.write_cursor.fetchone()

    new_princ_repayment_amount = principal_repayment_amount + applied.minor
    new_princ_repayment_usd_cents = int(math.ceil(new_princ_repayment_amount / rate_loan_to_usd))
    itgs.write_cursor.execute(
        Query.update(moneys)
        .set(moneys.amount, new_princ_repayment_amount)
        .set(moneys.amount_usd_cents, new_princ_repayment_usd_cents)
        .where(moneys.id == Parameter('%s'))
        .get_sql(),
        (principal_repayment_id,)
    )

    if new_princ_repayment_amount == principal_amount:
        itgs.write_cursor.execute(
            Query.update(loans)
            .set(loans.repaid_at, Now())
            .set(loans.updated_at, None)
            .where(loans.id == Parameter('%s'))
            .get_sql(),
            (loan_id,)
        )

    return (repayment_event_id, applied, remaining)
