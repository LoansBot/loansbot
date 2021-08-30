"""Tests that we can parse temporary ban details"""
import unittest
import helper  # noqa
from parsing.temp_ban_parser import parse_temporary_ban


class Test(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(
            parse_temporary_ban('1 day'),
            86400
        )

    def test_plural_days(self):
        self.assertEqual(
            parse_temporary_ban('5 days'),
            5 * 86400
        )

    def test_simple_newstyle(self):
        self.assertEqual(
            parse_temporary_ban('Ban changed to 28 days'),
            28 * 86400
        )
