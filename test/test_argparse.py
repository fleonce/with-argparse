import itertools
import sys
import unittest
from collections.abc import Iterable
from functools import wraps
from typing import Any, Optional, List, Set
from with_argparse import with_argparse
from tools import sys_args, foreach


class ArgparseTestCase(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
