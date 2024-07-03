import functools
import inspect
import typing
import warnings
from argparse import ArgumentParser

setup_root: typing.Union[typing.Callable, None]
try:
    from pyrootutils import setup_root
except ImportError:
    setup_root = None


config = {
    "enabled": True
}


def is_enabled():
    global config
    return config.get("enabled", True)


def set_config(key: str, state: bool):
    global config
    config[key] = state


def with_argparse(func):
    return _with_argparse(func, ignore_mapping=set())


def with_opt_argparse(*, ignore_mapping: set[str] = None, setup_cwd: bool = False, aliases: dict[str, list[str]] = None):
    def decorator(func):
        return _with_argparse(func, ignore_mapping=ignore_mapping or set(), setup_cwd=setup_cwd, aliases=aliases)

    return decorator


def _with_argparse(func, *, ignore_mapping: set[str], setup_cwd=False, aliases: dict[str, list[str]] = None):
    aliases = aliases or dict()

    @functools.wraps(func)
    def inner(*inner_args, **inner_kwargs):
        if not is_enabled():
            return func(*inner_args, **inner_kwargs)

        if setup_cwd:
            if setup_root is not None:
                setup_root(search_from=__file__, cwd=True, pythonpath=True)
            else:
                warnings.warn("Could not import setup_root from pyrootutils. Using 'setup_cwd=True' requires installing"
                              "pyrootutils")

        info = inspect.getfullargspec(func)
        args = ArgumentParser()
        mappings = {}

        def add_argument(x, typ, default, required):
            nonlocal mappings
            if typing.get_origin(typ) in {list, typing.Literal} and x.endswith("s") and x not in ignore_mapping:
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
            elif typing.get_origin(typ) in {list, typing.Literal}:
                origin = typing.get_origin(typ)
                type_args = typing.get_args(typ)
                if origin == list:
                    args.add_argument("--" + x, *x_alias, type=type_args[0], default=default, required=required, nargs="+")
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
            add_argument(arg, arg_type, arg_default, arg_required)
        for i, arg in enumerate(info.kwonlyargs or []):
            if arg in inner_kwargs:
                continue
            assert arg in info.annotations
            arg_type = info.annotations[arg]
            arg_default = info.kwonlydefaults.get(arg, None) if info.kwonlydefaults is not None else None
            arg_required = info.kwonlydefaults is None or arg not in info.kwonlydefaults
            add_argument(arg, arg_type, arg_default, arg_required)
        args = args.parse_args()
        args_dict = dict()
        for k, v in args.__dict__.items():
            if k in mappings:
                args_dict[mappings[k]] = v
            else:
                args_dict[k] = v

        return func(*inner_args, **args_dict, **inner_kwargs)

    return inner
