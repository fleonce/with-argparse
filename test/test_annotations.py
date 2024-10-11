import unittest

from with_argparse import with_argparse


class IgnoreTest(unittest.TestCase):
    def test_missing_arg_annotation(self):
        @with_argparse
        def wrapper(arg):
            return arg

        with self.assertRaisesRegex(
            ValueError,
            "Argument [a-z]+ must have a type annotation in order to be viable for argparse"
        ):
            wrapper()

    def test_missing_kwarg_annotation(self):
        @with_argparse
        def func(*, arg):
            return arg

        with self.assertRaisesRegex(
            ValueError,
            "Argument [a-z]+ must have a type annotation in order to be viable for argparse"
        ):
            func()
