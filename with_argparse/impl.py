import functools
import sys
import typing
from typing import Callable, Union, ParamSpec, TypeVar, overload, Optional, Mapping, _SpecialForm, Any
import warnings

from with_argparse.configure_argparse import WithArgparse

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


@overload
def with_argparse(
    *,
    ignore_keys: Optional[set[str]] = None,
    ignore_mapping: Optional[set[str]] = None,
    setup_cwd: Optional[bool] = None,
    aliases: Optional[Mapping[str, list[str]]] = None,
    use_glob: Optional[set[str]] = None,
    use_custom: Optional[Mapping[str, Callable[[Any], Any]]] = None,
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
    **kwargs: Callable[[Any], Any]
):
    aliases = aliases or dict()
    ignore_keys = ignore_keys or set()
    ignore_mapping = ignore_mapping or set()
    use_glob = use_glob or set()
    setup_cwd = setup_cwd or False
    use_custom = use_custom or dict()
    use_custom = dict(use_custom, **kwargs)

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
            )
            return parser.call(inner_args, inner_kwargs)
        return inner

    if func is None:
        return wrapper

    return wrapper(func)
