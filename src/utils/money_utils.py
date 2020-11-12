"""This utility has convenience functions for working with money objects"""
from pypika import PostgreSQLQuery as Query, Table, Parameter
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lbshared.money import Money
import query_helper


def find_or_create_money(itgs: LazyItgs, money: Money, amount_usd_cents: int) -> int:
    """Find or create a row in the moneys table that matches the given money
    object.

    Arguments:
    - `itgs (LazyItgs)`: The integrations to use to connect to networked
      services.
    - `money (Money)`: The money object to create a corresponding row for.
    - `amount_usd_cents (int)`: The money amount in USD cents at the current
      conversion rate.
    """
    currencies = Table('currencies')
    moneys = Table('moneys')

    (currency_id,) = query_helper.find_or_create_or_find(
        itgs,
        (
            Query.from_(currencies)
            .select(currencies.id)
            .where(currencies.code == Parameter('%s'))
            .get_sql(),
            (money.currency,)
        ),
        (
            Query.into(currencies)
            .columns(
                currencies.code,
                currencies.symbol,
                currencies.symbol_on_left,
                currencies.exponent
            )
            .insert(*(Parameter('%s') for _ in range(4)))
            .returning(currencies.id)
            .get_sql(),
            (
                money.currency,
                money.symbol or f' {money.currency}',
                money.symbol_on_left if money.symbol is not None else False,
                money.exp or 2
            )
        )
    )
    (money_id,) = query_helper.find_or_create_or_find(
        itgs,
        (
            Query.from_(moneys)
            .select(moneys.id)
            .where(moneys.currency_id == Parameter('%s'))
            .where(moneys.amount == Parameter('%s'))
            .where(moneys.amount_usd_cents == Parameter('%s'))
            .get_sql(),
            (currency_id, money.minor, amount_usd_cents)
        ),
        (
            Query.into(moneys)
            .columns(
                moneys.currency_id,
                moneys.amount,
                moneys.amount_usd_cents
            )
            .insert(*(Parameter('%s') for _ in range(3)))
            .returning(moneys.id)
            .get_sql(),
            (currency_id, money.minor, amount_usd_cents)
        )
    )
    return money_id
