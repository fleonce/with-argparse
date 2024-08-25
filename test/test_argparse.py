import itertools
import sys
import unittest
from collections.abc import Iterable
from functools import wraps
from typing import Any
from with_argparse import with_argparse


class sys_args:
    def __init__(self, **kwargs):
        self.args = list()
        self.oldargs = None

        self.args.append(sys.argv[0])
        for key, value in kwargs.items():
            if value is None:
                continue

            if isinstance(value, bool) and not value:
                continue
            self.args.append("--" + key)
            if isinstance(value, Iterable):
                for elem in value:
                    self.args.append(str(elem))
            else:
                self.args.append(str(value))
    def __enter__(self):
        self.oldargs = sys.argv
        sys.argv = self.args
    def __exit__(self, exc_type, exc_value, traceback):
        sys.argv = self.oldargs


def foreach(**setup: list[Any] | set[Any]):
    def inner(func):
        @wraps(func)
        def wrapper(self, **kwargs):
            combinations = []
            for arg, values in setup.items():
                values = [(arg, value) for value in values]
                combinations.append(values)
            combinations = itertools.product(*combinations)

            for combination in combinations:
                combination_kwargs = {arg: value for arg, value in combination}

                with self.subTest(**combination_kwargs):
                    func(self, **combination_kwargs, **kwargs)
        return wrapper
    return inner


class ArgparseTestCase(unittest.TestCase):

    def test_empty_argparse(self):
        @with_argparse()
        def wrapper():
            pass
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
