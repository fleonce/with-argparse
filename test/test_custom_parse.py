import logging
import unittest
from pathlib import Path
from typing import Optional

from tools import sys_args
from with_argparse import with_argparse

logging.basicConfig(
    level="DEBUG"
)


class CustomParseTest(unittest.TestCase):
    def test_parse_from_list_of_paths(self):
        class TestClass:
            @classmethod
            def from_string(cls, inp: list[Path]):
                return TestClass(inp)
            def __init__(self, *args):
                self.args = args
            def values(self):
                return self.args
        @with_argparse(use_custom={"value": TestClass.from_string})
        def wrapper(value: TestClass):
            return value

        with sys_args(value=[".", "."]):
            path = Path(".")
            self.assertEqual(wrapper().values()[0], [path, path])

    def test_parse_class_from_str(self):
        class TestClass:
            @classmethod
            def from_string(cls, inp: str) -> "TestClass":
                return TestClass(inp, "")

            def __init__(self, inp: str, _: str):
                self.inp = inp

            def value(self) -> str:
                return self.inp

        @with_argparse(use_custom={"a": TestClass.from_string})
        def wrapper(a: TestClass):
            return a

        with sys_args(a="abc"):
            self.assertEqual(wrapper().value(), "abc")

    def test_parse_kwarg(self):
        def wow_fn(inp: Optional[str]) -> int:
            return 42

        @with_argparse(value=wow_fn)
        def wrapper(value: int):
            return value

        with sys_args(value="any"):
            self.assertEqual(wrapper(), 42)