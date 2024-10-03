import unittest
from pathlib import Path

from with_argparse import with_argparse
from tools import sys_args


class GlobTestCase(unittest.TestCase):
    def test_glob_setting(self):
        @with_argparse(use_glob={"paths"})
        def wrapper(paths: list[Path]):
            return paths
        with sys_args(path="*"):
            out = wrapper()
            self.assertGreater(len(out), 1)

    def test_glob_set(self):
        @with_argparse(use_glob={"paths"})
        def wrapper(paths: set[Path]):
            return paths
        with sys_args(path="*"):
            out = wrapper()
            self.assertIsInstance(out, set)
            self.assertGreater(len(out), 1)


if __name__ == "__main__":
    unittest.main()
