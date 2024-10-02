import itertools
from functools import wraps
from typing import Any


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
