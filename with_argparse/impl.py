import functools
import inspect
import sys
import typing
from collections import defaultdict
from typing import Any, Callable, Union, ParamSpec, TypeVar, overload
import warnings
from argparse import ArgumentParser

from with_argparse.configure_argparse import WithArgparse
from with_argparse.utils import glob_to_path_list, flatten

setup_root: Union[Callable, None]
try:
    from pyrootutils import setup_root
except ImportError:
    setup_root = None

P = ParamSpec('P')
T = TypeVar('T')

LITERAL_TYPES = {
    typing.Literal,
}
if sys.version_info >= (3, 11, 0):
    LITERAL_TYPES |= {
        typing.LiteralString,
    }

SET_TYPES = {set, typing.Set}
LIST_TYPES = {list, typing.List}
SEQUENCE_TYPES = SET_TYPES | LIST_TYPES

ORIGIN_TYPES = {
    list,
    set,
    typing.Union,
    typing.Optional,
}
config = {
    "enabled": True
}


def is_enabled():
    global config
    return config.get("enabled", True)


def set_config(key: str, state: bool):
    global config
    config[key] = state


@overload
def with_argparse(func: Callable[P, T]) -> Callable[[], T]: ...


@overload
def with_argparse(
    *,
    ignore_mapping: set[str] = None,
    setup_cwd: bool = False,
    aliases: dict[str, list[str]] = None,
    use_glob: set[str] = None
) -> Callable[[Callable[P, T]], Callable[[], T]]: ...


def with_argparse(
    func=None,
    *,
    ignore_mapping: set[str] = None,
    setup_cwd: bool = False,
    aliases: dict[str, list[str]] = None,
    use_glob: set[str] = None,
):
    if func is None:
        def decorator(fn):
            return _configure_argparse(fn, ignore_mapping, setup_cwd, aliases, use_glob)
        return decorator
    return _configure_argparse(func, ignore_mapping, setup_cwd, aliases, use_glob)


def with_opt_argparse(
    *args, **kwargs
):
    warnings.warn(
        "with_opt_argparse is being deprecated and will be removed in a future release. Please use with_argparse instead",
        stacklevel=2
    )
    return with_argparse(*args, **kwargs)


def _configure_argparse(
    func,
    ignore_mapping: set[str] = None,
    setup_cwd=False,
    aliases: dict[str, list[str]] = None,
    use_glob: set[str] = None
):
    aliases = aliases or dict()
    ignore_mapping = ignore_mapping or set()
    use_glob = use_glob or set()

    @functools.wraps(func)
    def inner(*inner_args, **inner_kwargs):
        if not is_enabled():
            return func(*inner_args, **inner_kwargs)

        if setup_cwd:
            if setup_root is not None:
                setup_root(search_from=__file__, cwd=True, pythonpath=True)
            else:
                warnings.warn(
                    "Could not import setup_root from pyrootutils. Using 'setup_cwd=True' requires installing"
                    "pyrootutils"
                )

        parser = WithArgparse(
            func,
            aliases=aliases,
            ignore_rename=ignore_mapping,
            allow_glob=use_glob,
        )
        return parser.call(inner_args, inner_kwargs)

    return inner
