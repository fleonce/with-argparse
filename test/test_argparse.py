import logging
import unittest
from typing import Optional, Set

from tools import sys_args, foreach
from with_argparse import with_argparse

logging.basicConfig(
    level="DEBUG"
)


class ArgparseTestCase(unittest.TestCase):

    def test_multi_type_union(self):
        @with_argparse
        def func(inp: int | float):
            return inp

        value = 123.456
        with sys_args(inp=value):
            self.assertEqual(value, func())

    def test_python3_11_type_union(self):
        @with_argparse
        def func(inp: int | None):
            return inp

        with sys_args(inp=123):
            self.assertEqual(123, func())

    #    @foreach(inp={'microsoft/deberta-v3-large'})
    def test_arg(self):
        @with_argparse
        def func(model: str, generative: bool = False, compare_to: int = 0, trust_remote_code: bool = False):
            return model

        model = "microsoft"
        with sys_args():
            self.assertEqual(func(model, True), model)
            self.assertEqual(func(model=model, generative=True), model)
            self.assertEqual(func(model, generative=True), model)

    def test_empty_argparse(self):
        @with_argparse()
        def wrapper():
            pass

        wrapper()

    def test_argparse_with_optional(self):
        @with_argparse
        def wrapper(a: Optional[int] = None):
            return a

        wrapper()

    def test_list_argparse(self):
        @with_argparse
        def wrapper(a: Set[int] = None):
            return a

        with sys_args():
            wrapper()

    def test_empty_argparse_direct_decorator(self):
        @with_argparse
        def wrapper():
            pass

        wrapper()

    @foreach(default={0, None}, expect={42, 0})
    def test_argparse_int(self, default: int | None, expect: int | None):
        @with_argparse
        def wrapper(value: int = default) -> int:
            return value

        with sys_args(value=expect):
            self.assertEqual(wrapper(), expect)

    @foreach(expect={('a', 'b')})
    def test_argparse_set_type(self, expect):
        outer_set_t = set
        inner_set_t = type(next(iter(expect)))

        @with_argparse
        def wrapper(value: set[inner_set_t]):
            return value

        with sys_args(value=expect):
            self.assertEqual(wrapper(), outer_set_t(expect))

    @foreach(expect={('a', 'b')})
    def test_argparse_list_type(self, expect):
        outer_set_t = list
        inner_set_t = type(next(iter(expect)))

        @with_argparse
        def wrapper(value: list[inner_set_t]):
            return value

        with sys_args(value=expect):
            self.assertEqual(wrapper(), outer_set_t(expect))

    def test_unused_cli_input(self):
        @with_argparse
        def func(arg: str) -> str:
            return arg

        with sys_args(abc="123", arg="42"), self.assertRaises(SystemExit):
            func()

    def test_duplicate_inputs(self):
        @with_argparse
        def func(arg: str) -> str:
            return arg

        with sys_args(arg="456"):
            self.assertEqual(func(arg="123"), "456")
            self.assertEqual(func("123"), "456")
