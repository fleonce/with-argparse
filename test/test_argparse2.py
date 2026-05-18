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
            return args

        with sys_args():
            func()
