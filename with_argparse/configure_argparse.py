import inspect
import logging
import warnings
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from types import NoneType
from typing import Any, Set, List, get_origin, get_args, Union, Literal, Optional, Sequence, TypeVar, Iterable, \
    Callable, MutableMapping, Mapping
from with_argparse.utils import glob_to_path_list, flatten

SET_TYPES = {set, Set}
LIST_TYPES = {list, List}
SEQUENCE_TYPES = SET_TYPES | LIST_TYPES

_T = TypeVar("_T")

logger = logging.getLogger("with_argparse")


def first(iterable: Iterable[_T], default: Optional[_T] = None) -> _T:
    try:
        return next(iter(iterable))
    except StopIteration:
        if default is not None:
            return default
        raise


@dataclass
class _Argument:
    name: str
    type: type | Callable[[str], Any]
    default: Any
    required: bool
    nargs: bool
    choices: Optional[Sequence[Any]] = None
    action: Optional[str] = None


class WithArgparse:
    ignore_rename_sequences: set[str]
    argument_mapping: MutableMapping[str, str]
    argument_aliases: MutableMapping[str, Sequence[str]]
    post_parse_type_conversions: MutableMapping[str, list[Callable[[Any], Any]]]
    allow_glob: Optional[set[str]] = None

    def __init__(
        self,
        func,
        aliases: Optional[Mapping[str, Sequence[str]]] = None,
        ignore_rename: Optional[set[str]] = None,
        allow_glob: Optional[set[str]] = None,
    ):
        super().__init__()
        self.ignore_rename_sequences = ignore_rename or set()
        self.argument_mapping = dict()
        self.argument_aliases = dict(aliases or dict())
        self.post_parse_type_conversions = dict()
        self.allow_glob = allow_glob or set()

        self.func = func
        self.argparse = ArgumentParser()

    def _register_mapping(self): ...

    def _register_post_parse_type_conversion(self, key: str, func: Callable[[Any], Any]):
        if func is None:
            raise ValueError(f"Post parse type conversion for {key} must be non-None")

        if key not in self.post_parse_type_conversions:
            self.post_parse_type_conversions[key] = list()

        logger.debug(f"Registering post parse type conversion for {key}: {func.__name__} ({func})")
        self.post_parse_type_conversions[key].append(func)

    def call(self, args: Sequence[Any], kwargs: Mapping[str, Any]):
        info = inspect.getfullargspec(self.func)

        defaults = tuple(None for _ in range(len(info.args) - len(info.defaults or [])))
        if info.defaults:
            defaults = defaults + info.defaults
        else:
            defaults = defaults + tuple(None for _ in range(len(info.args)))

        for i, arg in enumerate(info.args or []):
            if i < len(args):
                continue

            if arg not in info.annotations:
                raise ValueError(f"Argument {arg} must have a type annotation in order to be viable for argparse")

            arg_type = info.annotations[arg]
            arg_default = defaults[i]
            arg_required = info.defaults is None or len(info.defaults) <= (len(info.args) - (i + 1))

            self._setup_argument(arg, arg_type, arg_default, arg_required)
        for i, arg in enumerate(info.kwonlyargs or []):
            if arg in kwargs:
                continue

            if arg not in info.annotations:
                raise ValueError(f"Argument {arg} must have a type annotation in order to be viable for argparse")

            arg_type = info.annotations[arg]
            arg_default = info.kwonlydefaults.get(arg, None) if info.kwonlydefaults is not None else None
            arg_required = info.kwonlydefaults is None or arg not in info.kwonlydefaults
            self._setup_argument(arg, arg_type, arg_default, arg_required)

        parsed_args = self.argparse.parse_args()
        args_dict: MutableMapping[str, Any]
        args_dict = dict()

        for key, value in parsed_args.__dict__.items():
            if key in self.argument_mapping:
                args_dict[self.argument_mapping[key]] = value
            else:
                args_dict[key] = value

        for key, conversion_functions in self.post_parse_type_conversions.items():
            initial_value = args_dict[key]
            if initial_value is None:
                args_dict[key] = initial_value
                continue

            value = initial_value
            for conversion_func in conversion_functions:
                value = conversion_func(value)
            args_dict[key] = value

        return self.func(*args, **args_dict, **kwargs)

    def _setup_argument(
        self,
        arg_name: str,
        arg_type: type,
        arg_default: Any,
        arg_required: bool
    ):
        args = self._dispatch_argparse_key_type(
            arg_name,
            arg_type,
            arg_default,
            arg_required
        )
        argparse_kwargs: dict[str, Any]
        argparse_kwargs = dict()

        if (
            args.action
            and args.action in {"store_true", "store_false"}
        ):
            argparse_kwargs["action"] = args.action
        else:
            argparse_kwargs["type"] = args.type
        argparse_kwargs["default"] = args.default
        argparse_kwargs["required"] = args.required
        if args.nargs:
            argparse_kwargs["nargs"] = "+"
        if args.choices:
            argparse_kwargs["choices"] = args.choices

        aliases = self.argument_aliases.get(arg_name, list())
        self.argparse.add_argument(
            "--" + args.name,
            *aliases,
            **argparse_kwargs
        )


    def _register_substitution(
        self,
        arg_name: str,
        replacement: str,
    ) -> str:
        """
        :param arg_name:
        :param replacement:
        :return: replacement
        """
        logger.debug(f"Registering substitution for {arg_name} with {replacement}")
        self.argument_mapping[replacement] = arg_name
        return replacement

    def _resolve_orig_arg_name(self, arg_name: str) -> str:
        while arg_name in self.argument_mapping:
            arg_name = self.argument_mapping[arg_name]
        return arg_name

    def _dispatch_argparse_key_type(
        self,
        arg_name: str,
        arg_type: type,
        arg_default: Any,
        arg_required: bool
    ) -> _Argument:
        logger.debug(f"Dispatch: {arg_name} ({arg_type}) default={arg_default}, required={arg_required}")
        pass
        origin_arg_type = get_origin(arg_type)
        if (
            origin_arg_type
            and origin_arg_type in SEQUENCE_TYPES
            and arg_name not in self.ignore_rename_sequences
            and arg_name.endswith("s")
        ):
            arg_name = self._register_substitution(arg_name, arg_name[:-1])

        if arg_type == bool:
            if arg_default is not None and not isinstance(arg_default, bool):
                raise ValueError(f"Default value for {arg_name} is of type {type(arg_default)}, but should be bool")

            arg_default = arg_default if arg_default is not None else False
            if arg_default:
                arg_name = self._register_substitution(arg_name, "no_" + arg_name)

            store_action = "store_true" if not arg_default else "store_false"
            return _Argument(
                arg_name,
                arg_type,
                arg_default,
                arg_required,
                nargs=False,
                action=store_action
            )
        elif (
            origin_arg_type
            and origin_arg_type in SEQUENCE_TYPES
        ):
            inner_arg_type = get_args(arg_type)[0]
            inner = self._dispatch_argparse_key_type(
                arg_name,
                inner_arg_type,
                arg_default,
                arg_required
            )

            if origin_arg_type is not list:
                orig_arg_name = self._resolve_orig_arg_name(arg_name)
                self._register_post_parse_type_conversion(orig_arg_name, origin_arg_type)

            return _Argument(
                inner.name,
                inner.type,
                inner.default,
                inner.required,
                True,
            )
        elif (
            origin_arg_type
            and origin_arg_type is Literal
        ):
            literal_values = get_args(arg_type)
            inner_args = set(map(type, literal_values))
            if len(set(inner_args)) == 1:
                inner_arg_type = first(inner_args, )
                inner = self._dispatch_argparse_key_type(
                    arg_name,
                    inner_arg_type,
                    arg_default,
                    arg_required,
                )

                return _Argument(
                    inner.name,
                    inner.type,
                    inner.default,
                    inner.required,
                    False,
                    literal_values,
                )
            else:
                raise NotImplementedError(
                    f"Literals with more than one inner type are not supported, "
                    f"got {inner_args} for {arg_name}"
                )
            pass
        elif (
            origin_arg_type
            and origin_arg_type is Union
        ):
            inner_arg_types = get_args(arg_type)
            if len(inner_arg_types) == 2 and NoneType in inner_arg_types:
                non_none_inner_arg_types = set(inner_arg_types) - {NoneType}
                inner_arg_type = first(non_none_inner_arg_types)
                if arg_default is not None:
                    warnings.warn(
                        f"Argument {arg_name} has type {arg_type} but cannot be None, "
                        f"got {arg_default} for default"
                    )
                if inner_arg_type is type(bool) and arg_default is None:
                    warnings.warn(
                        f"Argument {arg_name} has type {arg_type}, but cannot be None,"
                        f"got {arg_default} for default"
                    )
                inner = self._dispatch_argparse_key_type(
                    arg_name,
                    inner_arg_type,
                    arg_default,
                    arg_required
                )
                return inner
            raise NotImplementedError(arg_type)
        elif origin_arg_type:
            inner_args = get_args(arg_type)
            raise ValueError(
                "Unsupported origin type " + str(origin_arg_type) + " for type " + str(arg_type) + " "
                "with inner types " + str(inner_args)
            )
        else:
            orig_arg_name = self._resolve_orig_arg_name(arg_name)
            if (
                arg_type == Path
                and orig_arg_name in self.allow_glob
            ):
                self._register_post_parse_type_conversion(
                    orig_arg_name,
                    flatten,
                )

                return _Argument(
                    arg_name,
                    glob_to_path_list,
                    arg_default,
                    arg_required,
                    False,
                    None,
                    None,
                )
            return _Argument(
                arg_name,
                arg_type,
                arg_default,
                arg_required,
                False,
                None,
            )
