"""Tests that we can parse loan commands"""
import unittest
import helper  # noqa
from parsing.parser import Parser
import parsing.ext_tokens
import money

try:
    from summons.unpaid import PARSER
except:  # noqa
    PARSER = Parser(
        '$unpaid',
        [
            {'token': parsing.ext_tokens.create_user_token(), 'optional': False},
        ]
    )


class Test(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(
            PARSER.parse('$unpaid u/johndoe'),
            ['johndoe']
        )

    def test_leading_slash(self):
        self.assertEqual(
            PARSER.parse('$unpaid /u/johndoe'),
            ['johndoe']
        )

    def test_url(self):
        self.assertEqual(
            PARSER.parse('$unpaid [johndoe](https://reddit.com/u/johndoe)'),
            ['johndoe']
        )

    def test_url_slash(self):
        self.assertEqual(
            PARSER.parse('$unpaid [u/johndoe](https://reddit.com/u/johndoe)'),
            ['johndoe']
        )

    def test_url_slash_with_leading(self):
        self.assertEqual(
            PARSER.parse('$unpaid [/u/johndoe](https://reddit.com/u/johndoe)'),
            ['johndoe']
        )

    def test_bad_url(self):
        self.assertIsNone(
            PARSER.parse('$unpaid [johndoe2](https://reddit.com/u/johndoe)')
        )

    def test_url_explicit_variant(self):
        self.assertEqual(
            PARSER.parse('$unpaid [/u/johndoe](https://reddit.com/user/johndoe)'),
            ['johndoe']
        )

    def test_url_http_variant(self):
        self.assertEqual(
            PARSER.parse('$unpaid [/u/johndoe](http://reddit.com/u/johndoe)'),
            ['johndoe']
        )

    def test_url_query_params(self):
        self.assertEqual(
            PARSER.parse('$unpaid [/u/johndoe](http://reddit.com/u/johndoe?foo=7)'),
            ['johndoe']
        )

    def test_url_fragment_identifier(self):
        self.assertEqual(
            PARSER.parse('$unpaid [/u/johndoe](http://reddit.com/u/johndoe#garbage)'),
            ['johndoe']
        )

    def test_url_query_params_and_fragment(self):
        self.assertEqual(
            PARSER.parse('$unpaid [/u/johndoe](http://reddit.com/u/johndoe?foo=7#ninetytwo)'),
            ['johndoe']
        )


if __name__ == '__main__':
    unittest.main()
