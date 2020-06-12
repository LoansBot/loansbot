"""This module contains our extension tokens, ie., tokens that are actually
useful in and of themselves.
"""
import parsing.tokens as tkns
import lbshared.money as money
import re


def create_user_token():
    """Creates a token for identifying a user. This can either by a username
    prefixed by /u/, or a link to a user account with the text being the username,
    or a link to a user account with the text being the username prefixed by /u/.
    Furthermore, we ignore query parameters and fragments in links and we allow
    substituting /u/ with u/.
    """
    return tkns.FallbackToken([
        tkns.RegexToken(r'\A\s*/?u/(\w+)\s*', 1),
        tkns.RegexToken(
            r'\A\s*\[(?:/?u/)?(?P<username>\w+)\]' +
            r'\(https?://reddit.com/u(?:ser)?/(?P=username)(?:\?[^\)]*)?(?:#[^\)]*)?\)\s*',
            1
        )
    ])


def create_money_token():
    """Creates a token for identifying a money quantity. The value of the token
    is a Money DTO.

    Examples: $10, $10.12 CAD, USD 10$, £15, 5.50, JPY 32

    Note that some currencies have different minor currency exponents; e.g. JPY
    has no decimal place and KWD has 3 values after the decimal. We support
    these so long as they are set up in money.ISO_CODES_TO_EXP
    """
    def transform(match):
        groups = match.groupdict()
        if 'iso' in groups:
            iso = groups['iso']
        elif 'sym' in groups:
            iso = money.CURRENCY_SYMBOLS[groups['sym']]
        else:
            iso = 'USD'

        exp = money.ISO_CODES_TO_EXP[iso]
        new_amount_regex = (
            r'\A[0-9]+\Z' if exp == 0 else r'\A[0-9]+(?:\.[0-9]{' + str(exp) + r'})?\Z'
        )
        if not re.match(new_amount_regex, groups['amt']):
            return None

        # We manipulate the number as a string as it avoids floating point
        # rounding issues
        if '.' in groups['amt']:
            return money.Money(int(groups['amt'].replace('.', '')), iso)
        return money.Money(int(groups['amt'] + ''.join(['0'] * exp)), iso)

    iso_codes = '|'.join(money.ISO_CODES_TO_EXP.keys())
    symbols = '|'.join([k if k != '$' else r'\$' for k in money.CURRENCY_SYMBOLS.keys()])
    amount = r'[0-9]+(?:\.[0-9]{0,4})?'
    return tkns.TransformedToken(
        tkns.FallbackToken([
            tkns.RegexToken(
                r'\A\s*(?P<iso>' + iso_codes + r')\s+(?:' + symbols + r')?' +
                r'(?P<amt>' + amount + r')(?:' + symbols + r')?\s*', None),
            tkns.RegexToken(
                r'\A\s*(?:' + symbols + r')?(?P<amt>' + amount + r')' +
                r'(?:' + symbols + r')?\s+(?P<iso>' + iso_codes + r')\s*',
                None),
            tkns.RegexToken(r'\A\s*(?P<sym>' + symbols + r')(?P<amt>' + amount + r')\s*', None),
            tkns.RegexToken(r'\A\s*(?P<amt>' + amount + r')(?P<sym>' + symbols + r')\s*', None),
            tkns.RegexToken(r'\A\s*(?P<amt>' + amount + r')\s*', None),
        ]),
        transform
    )


def as_currency_token():
    """Creates a token for identifying a change-of-currency for a transaction.
    For example, a loan between two users which is made in EUR but should be
    tracked in JPY can be done with $loan 5 EUR AS JPY
    This will capture the 'AS JPY' part. The value of the token will be the
    iso4217 code (e.g., JPY)
    """
    iso_codes = '|'.join(money.ISO_CODES_TO_EXP.keys())

    return tkns.RegexToken(r'\A\s*[aA][sS]\s+(' + iso_codes + r')\s*', 1)


def create_uint_token():
    """Creates a token for identifying a nonnegative int."""
    return tkns.TransformedToken(
        tkns.RegexToken(r'\A\s*([0-9]+)\s*', 1),
        int
    )
