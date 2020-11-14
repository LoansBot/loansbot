"""Tests that we can parse loan commands"""
import unittest
import helper  # noqa
from parsing.parser import Parser
import parsing.ext_tokens
import lbshared.money as money

try:
    from summons.loan import PARSER
except:  # noqa
    PARSER = Parser(
        '$loan',
        [
            {'token': parsing.ext_tokens.create_money_token(), 'optional': False},
            {'token': parsing.ext_tokens.as_currency_token(), 'optional': True}
        ]
    )


class Test(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(
            PARSER.parse('$loan 15'),
            [money.Money(1500, 'USD'), None]
        )

    def test_symbol(self):
        self.assertEqual(
            PARSER.parse('$loan 15$'),
            [money.Money(1500, 'USD'), None]
        )

    def test_iso(self):
        self.assertEqual(
            PARSER.parse('$loan EUR 15'),
            [money.Money(1500, 'EUR'), None]
        )

    def test_cents(self):
        self.assertEqual(
            PARSER.parse('$loan 1.23'),
            [money.Money(123, 'USD'), None]
        )

    def test_cents_iso(self):
        self.assertEqual(
            PARSER.parse('$loan 1.23 CAD'),
            [money.Money(123, 'CAD'), None]
        )

    def test_comma(self):
        self.assertEqual(
            PARSER.parse('$loan $1,000'),
            [money.Money(100000, 'USD'), None]
        )

    def test_comma_and_period(self):
        self.assertEqual(
            PARSER.parse('$loan $1,000.00'),
            [money.Money(100000, 'USD'), None]
        )

    def test_convert(self):
        self.assertEqual(
            PARSER.parse('$loan 1.23 CAD AS JPY'),
            [money.Money(123, 'CAD'), 'JPY']
        )


if __name__ == '__main__':
    unittest.main()
