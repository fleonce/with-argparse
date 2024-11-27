import dataclasses
import inspect
import logging
import typing
import warnings
from argparse import ArgumentParser
from dataclasses import dataclass, _MISSING_TYPE
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
_NO_DEFAULT = None


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
    ignore_arg_keys: set[str]
    argument_mapping: MutableMapping[str, str]
    argument_aliases: MutableMapping[str, Sequence[str]]
    post_parse_type_conversions: MutableMapping[str, list[Callable[[Any], Any]]]
    allow_glob: set[str]
    allow_custom: Mapping[str, Callable[[Any], Any]]
    allow_dispatch_custom: bool

    func: Callable
    dataclass: Optional[type]

    def __init__(
        self,
        func_or_dataclass: Union[Callable, tuple[type, Callable]],
        aliases: Optional[Mapping[str, Sequence[str]]] = None,
        ignore_rename: Optional[set[str]] = None,
        ignore_keys: Optional[set[str]] = None,
        allow_glob: Optional[set[str]] = None,
        allow_custom: Optional[Mapping[str, Callable[[Any], Any]]] = None,
    ):
        super().__init__()
        self.ignore_rename_sequences = ignore_rename or set()
        self.ignore_arg_keys = ignore_keys or set()
        self.argument_mapping = dict()
        self.argument_aliases = dict(aliases or dict())
        self.post_parse_type_conversions = dict()
        self.allow_glob = allow_glob or set()
        self.allow_custom = allow_custom or dict()
        self.allow_dispatch_custom = True

        if isinstance(func_or_dataclass, tuple):
            if not inspect.isclass(func_or_dataclass[0]):
                raise ValueError("First argument must be a type")
            if not dataclasses.is_dataclass(func_or_dataclass[0]):
                raise ValueError("First argument must be a dataclass")
            self.dataclass = func_or_dataclass[0]
            self.func = func_or_dataclass[1]
        else:
            self.func = func_or_dataclass
            self.dataclass = None
        self.argparse = ArgumentParser()

    def _register_mapping(self): ...

    def _no_dispatch_custom(self):
        return NoDispatchCustom(self)

    def _register_post_parse_type_conversion(self, key: str, func: Callable[[Any], Any]):
        if func is None:
            raise ValueError(f"Post parse type conversion for {key} must be non-None")

        if key not in self.post_parse_type_conversions:
            self.post_parse_type_conversions[key] = list()

        logger.debug(f"Registering post parse type conversion for {key}: {func.__name__} ({func})")
        self.post_parse_type_conversions[key].append(func)

    def _call_dataclass(self, args: Sequence[Any], kwargs: Mapping[str, Any]):
        if args:
            raise ValueError("Positional argument overrides are not supported, yet")
        if kwargs:
            raise ValueError("Keyword argument overrides are not supported, yet")
        if self.dataclass is None:
            raise ValueError("self.dataclass cannot be None")

        field_hints = typing.get_type_hints(self.dataclass)
        for field in dataclasses.fields(self.dataclass):
            field_required = isinstance(field.default, _MISSING_TYPE)
            field_default = field.default if not field_required else None
            field_type = field.type
            if isinstance(field_type, str):
                field_type = field_hints.get(field.name)
            if not isinstance(field_type, type):
                raise ValueError(f"Cannot determine type of {field.name}, got {field_type}")
            self._setup_argument(
                field.name,
                field_type,
                field_default,
                field_required,
            )

        parsed_args = self.argparse.parse_args()
        return self.func(self.dataclass(**parsed_args.__dict__))

    def call(self, args: Sequence[Any], kwargs: Mapping[str, Any]):
        if self.dataclass is not None:
            return self._call_dataclass(args, kwargs)
        elif self.func is not None:
            return self._call_func(args, kwargs)
        else:
            raise ValueError("self.dataclass and self.func cannot both be None")


    def _call_func(self, args: Sequence[Any], kwargs: Mapping[str, Any]):
        info = inspect.getfullargspec(self.func)
        callable_args = info.args or []
        callable_kwonly = info.kwonlyargs or []
        callable_defaults = info.defaults or tuple()

        # the first N arguments have no default value
        # ... num positional args - num positional args w/ defaults
        num_non_default_pos_arg = len(callable_args) - len(callable_defaults)
        defaults = {i: None for i in range(num_non_default_pos_arg)}
        if callable_defaults:
            defaults.update({num_non_default_pos_arg + i: default for i, default in enumerate(callable_defaults)})

        overrides = dict()
        for i, arg in enumerate(args):
            if i >= len(callable_args):
                raise TypeError(
                    f"Received {len(args)} positional arguments to call {self.func}, "
                    f"function only accepts {len(callable_args)}"
                )
            ith_argname = callable_args[i]
            overrides[ith_argname] = arg
        for argname, argval in kwargs.items():
            if argname in overrides:
                raise TypeError(
                    f"Received override for argname {argname} by positional AND keyword argument, "
                    f"got {argname}={overrides[argname]} and {argname}={argval}"
                )
            overrides[argname] = argval

        setup_arguments = 0
        argument_names: list[str] = list()
        for i, arg in enumerate(info.args or []):
            argument_names.append(arg)
            if arg in self.ignore_arg_keys:
                continue

            if arg not in info.annotations:
                raise ValueError(f"Argument {arg} must have a type annotation in order to be viable for argparse")

            arg_type = info.annotations[arg]
            # default resolution via:
            # - function annotation name: typ = default
            # - function call override (positional) func(default)
            # - function call override (keyword) func(name=default)
            #
            # if function call override is present, it should be used as default, otherwise,
            # function annotation should be fallback
            is_non_default_arg = i < num_non_default_pos_arg
            arg_default = overrides.get(arg, defaults.get(i, _NO_DEFAULT))
            arg_required = is_non_default_arg and arg_default is None

            self._setup_argument(arg, arg_type, arg_default, arg_required)
            setup_arguments += 1
        for i, arg in enumerate(callable_kwonly):
            argument_names.append(arg)
            if arg in self.ignore_arg_keys:
                continue
            if arg in kwargs:
                raise ValueError(
                    f"Received multiple inputs for argument {arg}, received kwarg but argument is not "
                    f"ignored via '@with_argparse(ignore_keys=...)'")

            if arg not in info.annotations:
                raise ValueError(f"Argument {arg} must have a type annotation in order to be viable for argparse")

            arg_type = info.annotations[arg]
            arg_default = overrides.get(arg, (info.kwonlydefaults or dict()).get(arg, _NO_DEFAULT))
            arg_required = arg_default is _NO_DEFAULT
            if arg_default is _NO_DEFAULT:
                arg_default = None
            self._setup_argument(arg, arg_type, arg_default, arg_required)
            setup_arguments += 1

        if setup_arguments == 0:
            return self.func(*args, **kwargs)

        parsed_args = self.argparse.parse_args()
        args_dict: MutableMapping[str, Any]
        args_dict = dict()
        overriden_kwargs: MutableMapping[str, Any]
        overriden_kwargs = dict()

        ignored_field_args = [field for field in argument_names if field in self.ignore_arg_keys]
        for field_pos, field_name in enumerate(ignored_field_args):
            if field_pos < len(args):
                overriden_kwargs[field_name] = args[field_pos]
            else:
                if field_name not in kwargs:
                    raise ValueError(
                        f"Did not an argument for {field_name} (included in ignore_keys) via *args and "
                        f"**kwargs for calling {self.func}"
                    )
                overriden_kwargs[field_name] = kwargs[field_name]

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

        for key, value in overriden_kwargs.items():
            if key in args_dict:
                raise ValueError(
                    f"Recieved multiple inputs for argument {key}, {value} via function call "
                    f"and {args_dict[key]} via CLI. Consider adding '{key}' to 'ignore_keys'"
                )
            args_dict[key] = value

        return self.func(**args_dict)

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

        if (
            self.allow_dispatch_custom
            and arg_name in self.allow_custom
        ):
            custom_func = self.allow_custom[arg_name]
            sign = inspect.signature(custom_func)

            if len(sign.parameters) != 1:
                param_names = ''.join(param.annotation for name, param in sign.parameters.items())
                raise ValueError(
                    f"Argument {arg_name} received a custom parse function, however it accepts zero arguments, "
                    f"got '{custom_func}' with signature '[{param_names}] -> {sign.return_annotation}'"
                )

            only_param = first(sign.parameters.values())
            if only_param.annotation is only_param.empty:
                warnings.warn(
                    f"Argument {arg_name} received a custom parse function, however it has no type annotation. "
                    f"As a consequence, we cannot infer which type must be input, assuming 'str'"
                )
                custom_type = str
            else:
                custom_type = only_param.annotation

            with self._no_dispatch_custom():
                logger.debug(
                    f"A custom function for {arg_name} was configured. Dispatching with input argument type "
                    f"{custom_type} as is input to {custom_func.__name__}")
                inner = self._dispatch_argparse_key_type(
                    arg_name,
                    custom_type,
                    arg_default,
                    arg_required
                )

            self._register_post_parse_type_conversion(arg_name, custom_func)
            return inner

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
            inner_arg_types = get_args(arg_type)
            raise ValueError(
                "Unsupported origin type " + str(origin_arg_type) + " for type " + str(arg_type) + " "
                "with inner types " + str(inner_arg_types)
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

class NoDispatchCustom:
    def __init__(self, wa: WithArgparse):
        self.wa = wa
        self.orig = False

    def __enter__(self):
        self.orig = self.wa.allow_dispatch_custom
        self.wa.allow_dispatch_custom = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wa.allow_dispatch_custom = self.orig
