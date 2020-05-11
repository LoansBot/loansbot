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
    exp (int): The exponent for this currency type; will be fetched from iso
        codes to exp if not provided
    symbol (str, None): The symbol for this currency if there is a shorter
        alternative to the ISO code. For example '$' and symbol on left=true
        would become $15.00
    symbol_on_left (bool): True if the symbol should go left of the quantity,
        False if the symbol should go to the right of the quantiy.
    """
    def __init__(self, minor, currency, exp=None, symbol=None, symbol_on_left=False):
        tus.check(
            minor=(minor, int),
            currency=(currency, str),
            exp=(exp, (type(None), int)),
            symbol=(symbol, (type(None), str)),
            symbol_on_left=(symbol_on_left, bool)
        )
        self.minor = minor
        self.currency = currency
        self.exp = exp if exp is not None else ISO_CODES_TO_EXP[currency]
        self.symbol = symbol
        self.symbol_on_left = symbol_on_left

    def major_str(self):
        """Format the amount in the major currency. So e.g. 100 minor USD
        becomes $1.00
        """
        if self.exp == 0:
            return str(self.minor)
        major = self.minor / (10 ** self.exp)
        return ('{:.' + str(self.exp) + 'f}').format(major)

    def __repr__(self):
        return '{} {}'.format(self.major_str(), self.currency)

    def __str__(self):
        if self.symbol is None:
            return repr(self)

        if self.symbol_on_left:
            fmt = '{symbol}{major}'
        else:
            fmt = '{major}{symbol}'
        return fmt.format(major=self.major_str(), symbol=self.symbol)

    def __eq__(self, other):
        return (
            isinstance(other, Money) and
            other.minor == self.minor and
            other.currency == self.currency
        )
