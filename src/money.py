"""Describes simple DTO's for manipulating money amounts"""
import pytypeutils as tus

# We prefer peope use iso4217 codes, but these are some common
# non-contentious currency symbols for our audience, and even these are
# ambiguous
CURRENCY_SYMBOLS = {
    '$': 'USD',
    '€': 'EUR',
    '£': 'GBP'
}

ISO_CODES_TO_EXP = {
    'AUD': 2,
    'GBP': 2,
    'EUR': 2,
    'CAD': 2,
    'JPY': 0,
    'MXN': 2,
    'USD': 2
}


class Money:
    """Describes a monetary amount in the most granular unit of a given
    currency

    minor (int): The number of minor currency units
    currency (str): The uppercased ISO4217 currency code
    """
    def __init__(self, minor, currency):
        tus.check(minor=(minor, int), currency=(currency, str))
        self.minor = minor
        self.currency = currency

    def major_str(self):
        """Format the amount in the major currency. So e.g. 100 minor USD
        becomes $1.00
        """
        exp = ISO_CODES_TO_EXP[self.currency]
        if exp == 0:
            return str(self.minor)
        major = self.minor / (10 ** exp)
        return ('{:.' + str(exp) + 'f}').format(major)

    def __repr__(self):
        return '{} {}'.format(self.major_str(), self.currency)

    def __eq__(self, other):
        return (
            isinstance(other, Money) and
            other.minor == self.minor and
            other.currency == self.currency
        )
