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

        @with_dataclass(dataclass=Test)
        def func(args: Test):
            return args.param

        with sys_args(param="a", item=["a"]):
            self.assertEqual("a", func())
