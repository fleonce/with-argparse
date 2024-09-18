import functools
import inspect
import typing
from collections import defaultdict
from typing import Any, Callable, Union, ParamSpec, TypeVar, overload
import warnings
from argparse import ArgumentParser

from with_argparse.utils import glob_to_path_list, flatten

setup_root: Union[Callable, None]
try:
    from pyrootutils import setup_root
except ImportError:
    setup_root = None

P = ParamSpec('P')
T = TypeVar('T')

ORIGIN_TYPES = {
    list,
    set,
    typing.Literal
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
    ignore_keys: set[str] = None,
    ignore_mapping: set[str] = None,
    setup_cwd: bool = False,
    aliases: dict[str, list[str]] = None,
    use_glob: set[str] = None
) -> Callable[[Callable[P, T]], Callable[[], T]]: ...


def with_argparse(
    func=None,
    *,
    ignore_keys: set[str] = None,
    ignore_mapping: set[str] = None,
    setup_cwd: bool = False,
    aliases: dict[str, list[str]] = None,
    use_glob: set[str] = None,
):
    if func is None:
        def decorator(fn):
            return _configure_argparse(fn, ignore_keys, ignore_mapping, setup_cwd, aliases, use_glob)
        return decorator
    return _configure_argparse(func, ignore_keys, ignore_mapping, setup_cwd, aliases, use_glob)


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
    ignore_keys: set[str] = None,
    ignore_mapping: set[str] = None,
    setup_cwd=False,
    aliases: dict[str, list[str]] = None,
    use_glob: set[str] = None
):
    aliases = aliases or dict()
    ignore_keys = ignore_keys or set()
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

        info = inspect.getfullargspec(func)
        args = ArgumentParser()
        mappings = {}
        post_parse_type_conversions = defaultdict(list)

        def add_argument(x, typ, default, required):
            nonlocal mappings
            orig_x = x
            if typing.get_origin(typ) in ORIGIN_TYPES and x.endswith("s") and x not in ignore_mapping:
                mappings[x[:-1]] = x
                x = x[:-1]
            x_alias = aliases.get(x, [])
            if typ == bool:
                default = default if default is not None else False
                if default:
                    mappings["no_" + x] = x
                    args.add_argument(f"--no_" + x, *x_alias, action="store_false", default=default)
                else:
                    args.add_argument(f"--" + x, *x_alias, action="store_true", default=default)
            elif typing.get_origin(typ) in ORIGIN_TYPES:
                origin = typing.get_origin(typ)
                type_args = typing.get_args(typ)
                if origin in {set, list}:
                    inner_type = type_args[0]
                    if orig_x in use_glob:
                        inner_type = functools.partial(glob_to_path_list, map_t=inner_type)
                        post_parse_type_conversions[orig_x].append(flatten)
                    args.add_argument(
                        "--" + x, *x_alias, type=inner_type, default=default, required=required, nargs="+"
                    )
                    if origin != list:
                        post_parse_type_conversions[orig_x].append(origin)
                elif origin == typing.Literal:
                    choices = type_args
                    args.add_argument("--" + x, *x_alias, type=str, default=default, required=required, choices=choices)
                else:
                    raise ValueError("Unsupported origin type " + str(origin))
            elif typ == list[str]:
                args.add_argument("--" + x, *x_alias, type=str, default=default, required=required, nargs="+")
            elif typ == list[int]:
                args.add_argument("--" + x, *x_alias, type=int, default=default, required=required, nargs="+")
            else:
                args.add_argument("--" + x, *x_alias, type=typ, default=default, required=required)

        defaults = tuple(None for _ in range(len(info.args) - len(info.defaults or [])))
        if info.defaults:
            defaults = defaults + info.defaults
        else:
            defaults = defaults + tuple(None for _ in range(len(info.args)))
        for i, arg in enumerate(info.args or []):
            if i < len(inner_args):
                continue
            assert arg in info.annotations
            arg_type = info.annotations[arg]
            arg_default = defaults[i]
            arg_required = info.defaults is None or len(info.defaults) <= (len(info.args) - (i + 1))
            if arg in ignore_keys:
                continue
            add_argument(arg, arg_type, arg_default, arg_required)
        for i, arg in enumerate(info.kwonlyargs or []):
            if arg in inner_kwargs:
                continue
            assert arg in info.annotations
            arg_type = info.annotations[arg]
            arg_default = info.kwonlydefaults.get(arg, None) if info.kwonlydefaults is not None else None
            arg_required = info.kwonlydefaults is None or arg not in info.kwonlydefaults
            if arg in ignore_keys:
                continue
            add_argument(arg, arg_type, arg_default, arg_required)
        args = args.parse_args()
        args_dict = dict()
        for k, v in args.__dict__.items():
            if k in mappings:
                args_dict[mappings[k]] = v
            else:
                args_dict[k] = v
        for k, conversion_fns in post_parse_type_conversions.items():
            for conversion_fn in conversion_fns:
                args_dict[k] = conversion_fn(args_dict[k])

        return func(*inner_args, **args_dict, **inner_kwargs)

    return inner
