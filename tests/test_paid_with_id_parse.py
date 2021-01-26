"""Tests that we can parse $paid commands"""
import unittest
import helper  # noqa
from parsing.parser import Parser
import parsing.ext_tokens
import lbshared.money as money

try:
    from summons.paid_with_id import PARSER
except:  # noqa
    PARSER = Parser(
        ('$paid_with_id', '$paid\\_with\\_id'),
        [
            {'token': parsing.ext_tokens.create_uint_token(), 'optional': False},
            {'token': parsing.ext_tokens.create_money_token(), 'optional': False}
        ]
    )


class Test(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(
            PARSER.parse('$paid_with_id 1 2'),
            [1, money.Money(200, 'USD')]
        )

    def test_escaped(self):
        self.assertEqual(
            PARSER.parse('$paid\\_with\\_id 1 2'),
            [1, money.Money(200, 'USD')]
        )

    def test_malformed(self):
        self.assertIsNone(
            PARSER.parse('$paid\\_with\\_id 91888')
        )


if __name__ == '__main__':
    unittest.main()
