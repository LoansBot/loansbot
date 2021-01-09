"""Tests that we can parse $paid commands"""
import unittest
import helper  # noqa
from parsing.parser import Parser
import parsing.ext_tokens
import lbshared.money as money

try:
    from summons.paid import PARSER
except:  # noqa
    PARSER = Parser(
        '$paid',
        [
            {'token': parsing.ext_tokens.create_user_token(), 'optional': False},
            {'token': parsing.ext_tokens.create_money_token(), 'optional': False}
        ]
    )


class Test(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(
            PARSER.parse('$paid /u/johndoe 15'),
            ['johndoe', money.Money(1500, 'USD')]
        )

    def test_hyphenated_username(self):
        self.assertEqual(
            PARSER.parse('$paid u/Do-Re-Me $250'),
            ['Do-Re-Me', money.Money(25000, 'USD')]
        )

    def test_underscores_allowed_username(self):
        self.assertEqual(
            PARSER.parse('$paid u/Foo_The_Bar $37'),
            ['Foo_The_Bar', money.Money(3700, 'USD')]
        )

    def test_underscores_and_hyphens_allowed_username(self):
        self.assertEqual(
            PARSER.parse('$paid u/Foo_The-Bar $37'),
            ['Foo_The-Bar', money.Money(3700, 'USD')]
        )

    def test_user_missing_leading_slash(self):
        self.assertEqual(
            PARSER.parse('$paid u/johndoe 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/johndoe](https://www.reddit.com/u/johndoe) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_expanded(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/johndoe](https://www.reddit.com/user/johndoe) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_hyphen_link_expanded(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/john-doe](https://www.reddit.com/user/john-doe) 1'),
            ['john-doe', money.Money(100, 'USD')]
        )

    def test_user_link_no_leading_slash(self):
        self.assertEqual(
            PARSER.parse('$paid [u/johndoe](https://www.reddit.com/u/johndoe) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_trailing_slash(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/johndoe](https://www.reddit.com/u/johndoe/) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_expanded_trailing_slash(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/johndoe](https://www.reddit.com/user/johndoe/) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_http(self):
        self.assertEqual(
            PARSER.parse('$paid [u/johndoe](http://www.reddit.com/u/johndoe) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_noncanonical(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/johndoe](https://reddit.com/u/johndoe) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_noncanonical_expanded(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/johndoe](https://reddit.com/user/johndoe) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_noncanonical_trailing_slash(self):
        self.assertEqual(
            PARSER.parse('$paid [/u/johndoe](https://reddit.com/u/johndoe/) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )

    def test_user_link_noncanonical_no_leading_slash(self):
        self.assertEqual(
            PARSER.parse('$paid [u/johndoe](https://reddit.com/u/johndoe) 1'),
            ['johndoe', money.Money(100, 'USD')]
        )


if __name__ == '__main__':
    unittest.main()
