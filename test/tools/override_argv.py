import sys
from typing import Iterable


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
