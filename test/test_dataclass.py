import logging
import unittest
from dataclasses import dataclass
from typing import Literal

from tools import sys_args
from with_argparse import with_dataclass

logging.basicConfig(
    level="DEBUG"
)


class DataclassTest(unittest.TestCase):
    def test_dataclass(self):
        @dataclass
        class Test:
            param: Literal['a', 'b']
            items: list[str]

        @with_dataclass(args=Test)
        def func(args: Test):
            return args.param

        with sys_args(param="a", item=["a"]):
            self.assertEqual("a", func())

    def test_multi_dataclass(self):
        @dataclass
        class A:
            param: Literal['a', 'b']
        @dataclass
        class B:
            number: int

        @with_dataclass(A, B)
        def func(arg1: A, arg2: B):
            return len(arg1.param) + arg2.number

        with sys_args(param="a", number=1):
            self.assertEqual(2, func())