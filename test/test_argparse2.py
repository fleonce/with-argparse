import dataclasses
import unittest

from tools import sys_args
from with_argparse import with_dataclass


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
