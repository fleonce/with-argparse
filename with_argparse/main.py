import functools
from argparse import Namespace
from typing import Any, Callable, Literal, overload, ParamSpec, TypeVar

import attrs
from typing_extensions import Self

P = ParamSpec("P")
T = TypeVar("T")


@attrs.define
class GlobalState:
    disabled: bool = False
    partial: bool = False

    parse_hooks: list[Callable[[Namespace, list[str]], None]] = attrs.field(
        factory=list
    )


_global_state = GlobalState()


def _internal_global_state():
    return _global_state


@attrs.define
class ParseArgs:
    ignore: set[str] = attrs.field(factory=set)
    aliases: dict[str, list[str]] = attrs.field(factory=dict)
    parse_functions: dict[str, Callable[[str], Any]] = attrs.field(factory=dict)

    help_strategy: Literal["print-and-exit", "print-and-continue", "silent"] = (
        "print-and-exit"
    )

    def __attrs_post_init__(self):
        if self.parse_functions:
            raise TypeError(
                "Parsing functions for the following arguments were specified, "
                "however parse support has been removed. Please use attrs.Converter as an alternative."
            )


@attrs.define
class partial_argparse:  # noqa
    state: bool = attrs.field(init=False)
    remainder: list[str] = attrs.field(init=False, factory=list)

    def __enter__(self) -> Self:
        self.state = _global_state.partial
        _global_state.partial = True
        _global_state.parse_hooks.append(self)
        return self

    def __call__(self, parsed: Namespace, remaining: list[str]):
        # after hooks have been called, the remaining args are available from the
        # context manager variable
        self.remainder = remaining
        if self in _global_state.parse_hooks:
            _global_state.parse_hooks.remove(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        _global_state.partial = self.state
        if self in _global_state.parse_hooks:
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
        _global_state.disabled = self.state


@overload
def with_attrs(func: Callable[P, T], /) -> Callable[[], T]: ...


@overload
def with_attrs(
    *,
    parse_args: ParseArgs | None = None,
    strict: Literal[True] = True,
) -> Callable[[Callable[P, T]], Callable[[], T]]: ...


@overload
def with_attrs(
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = False,
) -> Callable[[Callable[P, T]], Callable[..., T]]: ...


def with_attrs(
    func: Callable | None = None,
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = True,
):
    return _with_argparse(func, parse_args=parse_args, strict=strict, func_type="attrs")


@overload
def with_dataclass(func: Callable[P, T], /) -> Callable[[], T]: ...


@overload
def with_dataclass(
    *,
    parse_args: ParseArgs | None = None,
    strict: Literal[True] = True,
) -> Callable[[Callable[P, T]], Callable[[], T]]: ...


@overload
def with_dataclass(
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = False,
) -> Callable[[Callable[P, T]], Callable[..., T]]: ...


def with_dataclass(
    func: Callable | None = None,
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = True,
):
    return _with_argparse(
        func, parse_args=parse_args, strict=strict, func_type="dataclass"
    )


@overload
def with_argparse(func: Callable[P, T], /) -> Callable[[], T]: ...


@overload
def with_argparse(
    *,
    parse_args: ParseArgs | None = None,
    strict: Literal[True] = True,
) -> Callable[[Callable[P, T]], Callable[[], T]]: ...


@overload
def with_argparse(
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = False,
) -> Callable[[Callable[P, T]], Callable[..., T]]: ...


def with_argparse(
    func: Callable | None = None,
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = True,
):
    return _with_argparse(func, parse_args=parse_args, strict=strict, func_type="infer")


def _with_argparse(
    func: Callable | None = None,
    *,
    parse_args: ParseArgs | None = None,
    strict: bool = True,
    func_type: Literal["attrs", "dataclass", "plain", "infer"] = "infer",
):
    # decorator-decorator path

    def decorator(decorated_func: Callable):
        @functools.wraps(decorated_func)
        def wrapper(*args, **kwargs):
            if _internal_global_state().disabled:
                return decorated_func(*args, **kwargs)

            from with_argparse.configure_argparse import WithArgparse

            if strict and (len(args) > 0 or len(kwargs) > 0):
                raise TypeError(
                    "In strict mode, arguments cannot be passed to the decorated dataclass function"
                )

            wa = WithArgparse(
                decorated_func, func_type, strict=strict, parse_args=parse_args
            )
            return wa.call(args, kwargs)

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


@overload
def script_argparse(func: Callable[P, T], /) -> T: ...


@overload
def script_argparse(
    *,
    parse_args: ParseArgs | None = None,
) -> Callable[[Callable[P, T]], T]: ...


def script_argparse(
    func: Callable | None = None, *, parse_args: ParseArgs | None = None
):
    if func is None:  # parse_args was specified

        def wrapper(decorated_func: Callable):
            configured_argparse = with_argparse(parse_args=parse_args, strict=True)
            return configured_argparse(decorated_func)()

        return wrapper
    else:
        return with_argparse(func)()
