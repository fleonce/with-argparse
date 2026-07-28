import dataclasses
import unittest

import attrs

from tools import sys_args
from with_argparse import no_argparse, partial_argparse, with_attrs, with_dataclass


class ArgParseTestCase(unittest.TestCase):
    def test_basic(self):
        @dataclasses.dataclass
        class A:
            field1: int

        @with_dataclass
        def func(args: A):
            return args.field1

        with sys_args():
            with self.assertRaises(SystemExit):
                func()

        with sys_args(field1="42"):
            self.assertEqual(42, func())

    def test_attrs(self):
        @attrs.define
        class A:
            field1: int

        @with_attrs(strict=False)
        def func(args: A):
            return args.field1

        with sys_args():
            with self.assertRaises(SystemExit):
                func()

        with sys_args(field1="42"):
            self.assertEqual(42, func())

        with sys_args(field1="42", test="test"), partial_argparse() as partial:
            func()
            self.assertEqual(["--test", "test"], partial.remainder)

        with sys_args(), no_argparse():
            self.assertEqual(42, func(A(42)))
