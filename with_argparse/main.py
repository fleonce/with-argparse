from __future__ import annotations
import argparse
import functools
import inspect
import pathlib
from argparse import Namespace
from typing import Callable, TypeVar, overload, Literal, Self, ParamSpec, Any

import attrs


@attrs.define
class GlobalState:
    disabled: bool = False
    partial: bool = False

    parse_hooks: list[Callable[[Namespace, list[str]], None]] = attrs.field(factory=list)

_global_state = GlobalState()


def _internal_global_state():
    return _global_state


@attrs.define
class ParseArgs:
    ignore: set[str] = attrs.field(factory=set)
    aliases: dict[str, list[str]] = attrs.field(factory=dict)
    parse_functions: dict[str, Callable[[str], Any]] = attrs.field(factory=dict)

    help_strategy: Literal["print-and-exit", "print-and-continue", "silent"] = "print-and-exit"

    def __attrs_post_init__(self):
        if self.parse_functions:
            raise TypeError(
                f"Parsing functions for the following arguments were specified, "
                f"however parse support has been removed. Please use attrs.Converter as an alternative."
            )


@attrs.define
class partial_argparse:  # noqa
    state: bool = attrs.field(init=False)
    remaining: list[str] = attrs.field(init=False)

    def __enter__(self) -> Self:
        self.state = _global_state.partial
        _global_state.partial = True
        _global_state.parse_hooks.append(self)
        return self

    def __call__(self, parsed: Namespace, remaining: list[str]):
        # after hooks have been called, the remaining args are available from the
        # context manager variable
        self.remaining = remaining
        _global_state.parse_hooks.remove(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        _global_state.partial = self.state
        _global_state.parse_hooks.remove(self)

    # todo: add __copy__ that does a shallow copy of this class
    #  and store those copies in the WithArgparse instances


@attrs.define
class no_argparse:
    state: bool = attrs.field(init=False)

    def __enter__(self):
        self.state = _global_state.disabled
        _global_state.disabled = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        _global_state.partial = self.state


@overload
def with_attrs[**P, T](func: Callable[P, T], /) -> Callable[[], T]:
    ...

@overload
def with_attrs[**P, T](
    *,
    parse_args: ParseArgs | None = None,
    strict: Literal[True] = True,
) -> Callable[[Callable[P, T]], Callable[[], T]]:
    ...

@overload
def with_attrs[**P, T](
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = False,
) -> Callable[[Callable[P, T]], Callable[..., T]]:
    ...


def with_attrs(func: Callable | None = None, *, parse_args: ParseArgs | None = None, strict: bool = True):
    # decorator-decorator path

    def decorator(decorated_func: Callable):
        @functools.wraps(decorated_func)
        def wrapper(*args, **kwargs):
            from with_argparse.configure_argparse import WithArgparse

            if strict and (len(args) > 0 or len(kwargs) > 0):
                raise TypeError("In strict mode, arguments cannot be passed to the decorated dataclass function")

            wa = WithArgparse(decorated_func, "infer", strict=strict, parse_args=parse_args)
            return wa.call(args, kwargs)
        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def script_argparse():
    raise NotImplementedError