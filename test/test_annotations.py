import unittest

from with_argparse import with_argparse


class IgnoreTest(unittest.TestCase):
    def test_missing_arg_annotation(self):
        @with_argparse
        def wrapper(arg):
            return arg

        with self.assertRaisesRegex(
            TypeError,
            "Function .+ must be strongly typed, however has no no type annotation for field '[a-z]+'"
        ):
            wrapper()

    def test_missing_kwarg_annotation(self):
        @with_argparse
        def func(*, arg):
            return arg

        with self.assertRaisesRegex(
            TypeError,
            "Function <function .+ must be strongly typed, however has no no type annotation for field '[a-z]+'"
        ):
            func()
