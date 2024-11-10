import logging
import unittest

from tools import sys_args
from with_argparse import with_argparse

logging.basicConfig(
    level="DEBUG"
)


class IgnoreTest(unittest.TestCase):
    def test_ignore_single_param(self):
        @with_argparse(ignore_keys={"arg"})
        def wrapper(arg: str) -> str:
            return arg

        self.assertEqual("abc", wrapper("abc"))

    def test_ignore_multi_param(self):
        @with_argparse(ignore_keys={"arg"})
        def wrapper(arg: str, inp: str) -> str:
            return inp + arg

        with self.assertRaises(SystemExit):
            wrapper(arg="abc")
        with self.assertRaises(SystemExit):
            wrapper("abc")

        with sys_args(inp="42"):
            self.assertEqual("42abc", wrapper(arg="abc"))
            self.assertEqual("42abc", wrapper("abc"))

    def test_ignore_kwarg_multi_param(self):
        @with_argparse(ignore_keys={"arg"})
        def wrapper(inp: str, arg: str) -> str:
            return arg

        with sys_args(inp="42"):
            self.assertEqual("value", wrapper("value"))
            self.assertEqual("value", wrapper(arg="value"))

    def test_kwonly_kwarg_multi_param(self):
        @with_argparse(ignore_keys={"arg"})
        def wrapper(*, inp: str, arg: str) -> str:
            return inp + arg

        with self.assertRaises(TypeError):
            wrapper("abc")
        with self.assertRaises(SystemExit):
            wrapper(arg="abc")

        with sys_args(inp="a"):
            with self.assertRaises(TypeError):
                wrapper("b")
            self.assertEqual("ab", wrapper(arg="b"))
