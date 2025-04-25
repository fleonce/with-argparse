import functools
import sys
import typing
from typing import Callable, Union, ParamSpec, TypeVar, overload, Optional, Mapping, _SpecialForm, Any
import warnings

from with_argparse.configure_argparse import WithArgparse, DataclassConfig
from with_argparse.types import DataclassInstance

try:
    from pyrootutils import setup_root as setup_root_fn

    setup_root: Union[Callable, None] = setup_root_fn
except ImportError:
    setup_root_fn = None

P = ParamSpec('P')
T = TypeVar('T')

LITERAL_TYPES: set[type | _SpecialForm] = {
    typing.Literal,
}
if sys.version_info[:2] >= (3, 11):
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


def with_dataclass(
    *pos: type[DataclassInstance],
    allow_glob: Optional[set[str]] = None,
    partial_parse: Optional[bool] = None,
    **kwargs: type[DataclassInstance],
):
    if not pos:
        pos = tuple()
    else:
        pass
        # raise NotImplementedError(
        #   f"In the future, I would entertain the idea to get the dataclass instances from the "
        #   f"method spec instead of specifying it again via positional or keyword arguments"
        # )

    def wrapper(fn):
        @functools.wraps(fn)
        def inner(*inner_args, **inner_kwargs):
            if not is_enabled():
                return fn(*inner_args, **inner_kwargs)

            parser = WithArgparse(
                DataclassConfig(
                    fn,
                    pos,
                    kwargs,
                ),
                allow_glob=allow_glob,
                partial_parse=partial_parse,
            )
            return parser.call(inner_args, inner_kwargs)
        return inner
    return wrapper


@overload
def with_argparse(
    *,
    ignore_keys: Optional[set[str]] = None,
    ignore_mapping: Optional[set[str]] = None,
    setup_cwd: Optional[bool] = None,
    aliases: Optional[Mapping[str, list[str]]] = None,
    use_glob: Optional[set[str]] = None,
    use_custom: Optional[Mapping[str, Callable[[Any], Any]]] = None,
    partial_parse: Optional[bool] = None,
    **kwargs: Callable[[Any], Any]
) -> Callable[[Callable[P, T]], Callable[[], T]]: ...

@overload
def with_argparse(func: Callable[P, T], /) -> Callable[[], T]: ...

def with_argparse(
    func=None,
    *,
    ignore_keys: Optional[set[str]] = None,
    ignore_mapping: Optional[set[str]] = None,
    setup_cwd: Optional[bool] = None,
    aliases: Optional[Mapping[str, list[str]]] = None,
    use_glob: Optional[set[str]] = None,
    use_custom: Optional[Mapping[str, Callable[[Any], Any]]] = None,
    partial_parse: Optional[bool] = None,
    **kwargs: Callable[[Any], Any]
):
    aliases = aliases or dict()
    ignore_keys = ignore_keys or set()
    ignore_mapping = ignore_mapping or set()
    use_glob = use_glob or set()
    setup_cwd = setup_cwd or False
    use_custom = use_custom or dict()
    use_custom = dict(use_custom, **kwargs)
    partial_parse = partial_parse or False

    def wrapper(fn):
        @functools.wraps(fn)
        def inner(*inner_args, **inner_kwargs):
            if not is_enabled():
                return fn(*inner_args, **inner_kwargs)

            if setup_cwd:
                if setup_root is not None:
                    setup_root(search_from=__file__, cwd=True, pythonpath=True)
                else:
                    warnings.warn(
                        "Could not import setup_root from pyrootutils. Using 'setup_cwd=True' requires installing"
                        "pyrootutils"
                    )

            parser = WithArgparse(
                fn,
                aliases=aliases,
                ignore_rename=ignore_mapping,
                ignore_keys=ignore_keys,
                allow_glob=use_glob,
                allow_custom=use_custom,
                partial_parse=partial_parse
            )
            return parser.call(inner_args, inner_kwargs)
        return inner

    if func is None:
        return wrapper

    return wrapper(func)


@overload
def script_argparse(
    *,
    ignore_keys: Optional[set[str]] = None,
    ignore_mapping: Optional[set[str]] = None,
    setup_cwd: Optional[bool] = None,
    aliases: Optional[Mapping[str, list[str]]] = None,
    use_glob: Optional[set[str]] = None,
    use_custom: Optional[Mapping[str, Callable[[Any], Any]]] = None,
    partial_parse: Optional[bool] = None,
    **kwargs: Callable[[Any], Any]
) -> Callable[[Callable[P, T]], Callable[[], T]]: ...

@overload
def script_argparse(func: Callable[P, T], /) -> Callable[[], T]: ...

def script_argparse(
    func=None,
    *,
    ignore_keys: Optional[set[str]] = None,
    ignore_mapping: Optional[set[str]] = None,
    setup_cwd: Optional[bool] = None,
    aliases: Optional[Mapping[str, list[str]]] = None,
    use_glob: Optional[set[str]] = None,
    use_custom: Optional[Mapping[str, Callable[[Any], Any]]] = None,
    partial_parse: Optional[bool] = None,
    **kwargs: Callable[[Any], Any]
):
    decorator_func = with_argparse(
        ignore_keys=ignore_keys,
        ignore_mapping=ignore_mapping,
        setup_cwd=setup_cwd,
        aliases=aliases,
        use_glob=use_glob,
        use_custom=use_custom,
        partial_parse=partial_parse,
        **kwargs,
    )

    argparse_func = decorator_func(func)
    argparse_result = argparse_func()

    def producer_func():
        return argparse_result
    return producer_func