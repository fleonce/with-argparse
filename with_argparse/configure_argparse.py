import argparse
import dataclasses
import inspect
import logging
import sys
import typing
import warnings
from argparse import ArgumentParser
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, is_dataclass
from functools import partial
from pathlib import Path
from types import GenericAlias, NoneType, UnionType
from typing import (
    Any,
    Callable,
    get_args,
    get_origin,
    Iterable,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Set,
    TypeVar,
    Union,
)

import attrs
from typing_extensions import Self

from with_argparse.main import _internal_global_state, ParseArgs
from with_argparse.setup import config
from with_argparse.utils import flatten, glob_to_paths

SET_TYPES = {set, Set}
LIST_TYPES = {list, List}
SEQUENCE_TYPES = SET_TYPES | LIST_TYPES

_T = TypeVar("_T")

logger = logging.getLogger("with_argparse")
_NO_DEFAULT = None


class MissingArgument:
    __slots__ = ()


MISSING_ARG = MissingArgument()


def _help_called():
    parser = ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true", default=False)
    parsed = parser.parse_known_args()[0]
    return parsed.help is True


def first(iterable: Iterable[_T], default: Optional[_T] = None) -> _T:
    try:
        return next(iter(iterable))
    except StopIteration:
        if default is not None:
            return default
        raise


@attrs.define
class _Argument:
    name: str
    type: type | Callable[[str], Any]
    default: Any
    required: bool
    nargs: bool
    choices: Optional[Sequence[Any]] = None
    action: Optional[str] = None


def _infer_func_type(
    func: Callable, parse_args: ParseArgs
) -> Literal["plain", "attrs", "dataclass"]:
    signature = inspect.getfullargspec(func)

    for arg in signature.args + signature.kwonlyargs:
        if arg in parse_args.ignore:
            continue

        if arg not in signature.annotations:
            raise TypeError(
                f"Function {func!r} must be strongly typed, "
                f"however has no no type annotation for field {arg!r}"
            )
        arg_type = signature.annotations[arg]
        if isinstance(arg_type, str):
            arg_type = typing.get_type_hints(func)[arg]

        if attrs.has(arg_type):
            return "attrs"
        elif is_dataclass(arg_type):
            return "dataclass"

    return "plain"


@dataclass
class DataclassConfig:
    func: Callable


class WithArgparse:
    ignore_rename_sequences: set[str]
    ignore_arg_keys: set[str]
    argument_mapping: MutableMapping[str, str]
    argument_aliases: MutableMapping[str, Sequence[str]]
    post_parse_type_conversions: MutableMapping[str, list[Callable[[Any], Any]]]
    allow_glob: set[str]
    allow_custom: Mapping[str, Callable[[Any], Any]]
    allow_dispatch_custom: bool
    partial_parse: bool
    remaining_args: list[str]

    func: Callable
    func_type: Literal["attrs", "dataclass", "plain"]
    strict: bool

    def __init__(
        self,
        func: Callable,
        func_type: Literal["attrs", "dataclass", "plain", "infer"] = "infer",
        strict: bool = True,
        aliases: Optional[Mapping[str, Sequence[str]]] = None,
        ignore_rename: Optional[set[str]] = None,
        ignore_keys: Optional[set[str]] = None,
        allow_glob: Optional[set[str]] = None,
        allow_custom: Optional[Mapping[str, Callable[[Any], Any]]] = None,
        partial_parse: Optional[bool] = None,
        partial_parse_pass_remaining_args: Optional[bool] = None,
        add_help: Optional[bool] = None,
        on_help: Optional[Callable[[Self], Any]] = None,
        parse_args: ParseArgs | None = None,
    ):
        super().__init__()

        if parse_args is None:
            parse_args = ParseArgs(set())

        if func_type == "infer":
            func_type = _infer_func_type(func, parse_args)

        if add_help is None:
            add_help = config["add_help"]

        self.ignore_rename_sequences = ignore_rename or set()
        self.ignore_arg_keys = ignore_keys or set()
        self.argument_aliases = dict(aliases or dict())
        self.post_parse_type_conversions = dict()
        self.allow_glob = allow_glob or set()
        self.allow_custom = allow_custom or dict()
        self.allow_dispatch_custom = True
        self.partial_parse = partial_parse or False
        self.remaining_args = []
        self.partial_parse_pass_remaining_args = (
            partial_parse_pass_remaining_args or False
        )
        self.on_help = on_help
        self.add_help = add_help

        self.func = func
        self.func_type = func_type
        self.strict = strict
        self._help_caught = False

        self.parse_args = parse_args
        self._reset_argparse()

    def _register_mapping(self): ...

    def _no_dispatch_custom(self):
        return NoDispatchCustom(self)

    def _register_post_parse_type_conversion(
        self, key: str, func: Callable[[Any], Any]
    ):
        if func is None:
            raise ValueError(f"Post parse type conversion for {key} must be non-None")

        if key not in self.post_parse_type_conversions:
            self.post_parse_type_conversions[key] = list()

        logger.debug(
            f"Registering post parse type conversion for {key}: {func.__name__} ({func})"
        )
        self.post_parse_type_conversions[key].append(func)

    def _parser_parse(
        self,
        parser: argparse.ArgumentParser,
        args: Optional[Sequence[str]] = None,
        partial_parse: bool = False,
    ) -> tuple[argparse.Namespace, list[str]]:
        if partial_parse:
            return parser.parse_known_args(args)
        else:
            return parser.parse_args(args), []

    def _argparse_parse(self):
        if self.partial_parse:
            namespace, self.remaining_args = self.argparse.parse_known_args()
        else:
            namespace = self.argparse.parse_args()
        if self.on_help is not None and callable(self.on_help) and "_help" in namespace:
            if namespace._help:
                self.on_help(self)
        return namespace

    def _print_usage(
        self,
        parser: argparse.ArgumentParser | OrderedDict[str, argparse.ArgumentParser],
        short: bool = False,
    ):
        if isinstance(parser, argparse.ArgumentParser):
            if short:
                parser.print_usage()
            else:
                parser.print_help()
        else:
            if len(parser) == 1:
                self._print_usage(first(parser.values()), short=short)
                return
            usage = ""
            for field_name in parser.keys():
                formatted_usage_or_help = (
                    parser[field_name].format_usage()
                    if short
                    else parser[field_name].format_help()
                )
                usage += "--- help for field name %s ---\n %s\n\n" % (
                    field_name,
                    formatted_usage_or_help,
                )
            first(parser.values()).exit(2, usage)

    def _call_any(self, args: Sequence[Any], kwargs: Mapping[str, Any]):
        """
        This function identifies the attrs function arguments inside this function,
        parses these and calls the configured function with the parsed argument attrs instances

        Args:
             args: Positional arguments to call the function with
             kwargs: Keyword-only arguments to call the function with

        """
        orig_args = args
        orig_kwargs = kwargs

        signature = inspect.getfullargspec(self.func)
        if signature.varargs:
            raise TypeError("Variational positional arguments are not supported")
        if signature.varkw and self.strict:
            raise TypeError("Variational keyword arguments are not supported")
        if self.strict and len(args) > 0:
            raise TypeError(
                "In strict mode, providing positional arguments is unsupported"
            )
        if self.strict and len(kwargs) > 0:
            raise TypeError(
                "In strict mode, providing keyword arguments is unsupported"
            )

        if len(args) > len(signature.args):
            raise TypeError(
                f"Received more positional arguments ({len(args)}) to call {self.func!r} than this function receives: {len(signature.args)}"
            )

        args_to_parse = OrderedDict()

        call_args = {}
        registered_args: MutableMapping[str, tuple[Any, ...]] = {}
        registering_fields: Mapping[str, set[type]] = defaultdict(set)

        for pos, name in enumerate(signature.args + signature.kwonlyargs):
            if pos < len(orig_args):
                # this arg is provided as an argument already
                call_args[name] = orig_args[pos]
                continue
            elif name in orig_kwargs:
                # this arg is provided as an argument already
                call_args[name] = orig_kwargs[name]
                continue

            if name not in signature.annotations:
                raise TypeError(
                    f"Function {self.func!r} must be strongly typed. "
                    f"The non-provided argument {name!r} is missing a type signature."
                )

            typ = signature.annotations[name]
            if isinstance(typ, str):
                typ = typing.get_type_hints(self.func)[name]

            if self.func_type == "plain":
                if attrs.has(typ) or is_dataclass(typ):
                    raise TypeError(
                        f"In plain mode, arguments cannot be dataclasses. "
                        f"Field {name!r} of function {self.func!r} is an attrs or dataclass type: {typ!r}."
                    )

            elif self.func_type == "dataclass":
                if not is_dataclass(typ):
                    raise TypeError(
                        f"Field {name!r} of function {self.func!r} must be a dataclass instance, got {typ}"
                    )
            elif self.func_type == "attrs":
                if not attrs.has(typ):
                    raise TypeError(
                        f"Field {name!r} of function {self.func!r} must be an attrs instance, got {typ}"
                    )
            args_to_parse[name] = typ

        if self.func_type == "plain":
            positional_defaults = signature.defaults or ()
            non_default_positional_args = len(signature.args) - len(positional_defaults)
            positional_defaults = (
                MISSING_ARG,
            ) * non_default_positional_args + positional_defaults

            arg_defaults = {
                arg: positional_defaults[i] for i, arg in enumerate(signature.args)
            }
            arg_defaults = arg_defaults | (signature.kwonlydefaults or {})

            for arg, typ in args_to_parse.items():
                arg_required = (
                    arg not in arg_defaults or arg_defaults[arg] is MISSING_ARG
                )
                arg_default = arg_defaults.get(arg, MISSING_ARG)

                if (
                    arg_default is not MISSING_ARG
                    and (
                        (
                            not isinstance(typ, UnionType)
                            and not isinstance(typ, GenericAlias)
                        )
                        or (
                            isinstance(typ, UnionType)
                            and all(
                                not isinstance(typ_arg, GenericAlias)
                                for typ_arg in typ.__args__
                            )
                        )
                    )
                    and not isinstance(arg_default, typ)
                ):
                    raise TypeError(
                        f"Invalid default value for argument {arg!r}: "
                        f"got {arg_default!r} ({type(arg_default)!r}) for type {typ!r}"
                    )

                self._setup_argument(
                    arg,
                    typ,
                    arg_default,
                    arg_required,
                    None,
                    self.parse_args.aliases.get(arg, None),
                )
        else:
            for arg, typ in args_to_parse.items():
                # at this point, typ is a dataclass or attrs instance, depending on self.func_type
                fields = (
                    dataclasses.fields(typ)
                    if self.func_type == "dataclass"
                    else attrs.fields(typ)
                )
                field_hints = typing.get_type_hints(typ)
                missing_obj = (
                    dataclasses.MISSING
                    if self.func_type == "dataclass"
                    else attrs.NOTHING
                )
                for field in fields:
                    field_required = field.default is missing_obj
                    field_default = field.default if not field_required else MISSING_ARG
                    field_type = field.type
                    if isinstance(field_type, str):
                        field_type = field_hints.get(field.name)
                    if field_type is None:
                        raise TypeError(
                            f"Invalid field type {type(field_type)!r} "
                            f"for function argument {arg!r} and field name {field.name!r}"
                        )

                    field_help = None
                    if field.metadata is not None and "help" in field.metadata:
                        field_help = str(field.metadata["help"])

                    field_aliases = None
                    if field.metadata is not None and "aliases" in field.metadata:
                        field_aliases = field.metadata["aliases"]

                    field_args = (
                        field.name,
                        field_type,
                        field_default,
                        field_required,
                        field_help,
                        field_aliases,
                        field.kw_only,
                    )
                    if (
                        field.name in registered_args
                        and registered_args[field.name] != field_args
                    ):
                        previous_registrations = list(
                            sorted(registering_fields[field.name], key=str)
                        )

                        other_args = registered_args[field.name]
                        mismatch_reasons = []
                        if field_args[1] != other_args[1]:
                            mismatch_reasons.append(
                                f"type mismatch: {field_args[1]!r} vs {other_args[1]!r}"
                            )
                        if field_args[2] != other_args[2]:
                            mismatch_reasons.append(
                                f"default value mismatch: {field_args[2]!r} vs {other_args[2]!r}"
                            )
                        if field_args[3] != field_args[3]:
                            mismatch_reasons.append(
                                f"required value mismatch: {field_args[3]!r} vs {other_args[3]!r}"
                            )
                        if field_args[4] != field_args[4]:
                            mismatch_reasons.append(
                                f"help mismatch: {field_args[4]!r} vs {other_args[4]!r}"
                            )
                        if field_args[5] != field_args[5]:
                            mismatch_reasons.append(
                                f"aliases mismatch: {field_args[5]!r} vs {other_args[5]!r}"
                            )

                        if len(mismatch_reasons) == 0:
                            mismatch_reasons = ["unknown reason"]
                        mismatch_reason = ",".join(mismatch_reasons)

                        raise TypeError(
                            f"Mismatch in overlapping argument {field.name!r}: "
                            f"Previous instances ({previous_registrations}) have the following differences: "
                            f"{mismatch_reason}"
                        )

                    self._setup_argument(
                        field.name,
                        field_type,
                        field_default,
                        field_required,
                        field_help,
                        field_aliases,
                    )

                    registered_args[field.name] = field_args
                    registering_fields[field.name].add(typ)

        try:
            if _help_called():
                self._handle_help_call()
            namespace, remaining = self.argparse.parse_known_args()
            for hook in _internal_global_state().parse_hooks:
                hook(namespace, remaining)

            # todo: use copy of internal state within this object
            if len(remaining) > 0 and not _internal_global_state().partial:
                remaining_str = " ".join(map(repr, remaining))
                raise argparse.ArgumentError(
                    argument=None,
                    message=f"failed to parse the following args: {remaining_str}",
                )
        except argparse.ArgumentError as err:
            self._print_usage(self.argparse, short=False)
            print("error:", err.message, file=sys.stderr)
            sys.exit(2)

        args_dict = self._apply_post_parse_conversions(namespace.__dict__, dict())

        if self.func_type in {"attrs", "dataclass"}:
            registering_types = defaultdict(set)
            for field_name, field_types in registering_fields.items():
                for field_type in field_types:
                    registering_types[field_type].add(field_name)

            for arg, typ in args_to_parse.items():
                field_kwargs = {}
                for field_name in registering_types[typ]:
                    field_value = args_dict.get(field_name)
                    if field_value is not MISSING_ARG:
                        field_kwargs[field_name] = field_value

                # instantiate the attrs/dataclass type with its keyword arguments
                typ_value = typ(**field_kwargs)

                call_args[arg] = typ_value
        else:
            for arg, value in args_dict.items():
                if arg in call_args:
                    raise ValueError(
                        f"Illegal state, argument {arg!r} is already registered as a call arg: {call_args!r}"
                    )

                call_args[arg] = value

        positional_args: tuple[Any, ...] = ()
        kwonly_args = {}
        for arg, val in call_args.items():
            if isinstance(val, MissingArgument):
                raise TypeError("Invalid state")

        for arg in signature.args:
            positional_args += (call_args.pop(arg),)
        for arg in signature.kwonlyargs:
            kwonly_args[arg] = call_args.pop(arg)

        return self.func(*positional_args, **kwonly_args)

    def call(self, args: Sequence[Any], kwargs: Mapping[str, Any]):
        return self._call_any(args, kwargs)

    def _apply_post_parse_conversions(
        self, parsed_args: Mapping[str, Any], out: MutableMapping[str, Any] | None
    ) -> MutableMapping[str, Any]:
        out = out or dict()
        out.update(parsed_args)
        for key, conversion_functions in self.post_parse_type_conversions.items():
            initial_value = parsed_args[key]
            if initial_value is None:
                out[key] = initial_value
                continue

            value = initial_value
            for conversion_func in conversion_functions:
                value = conversion_func(value)
            out[key] = value
        return out

    def reset(self):
        self._reset_argparse()
        self.post_parse_type_conversions.clear()

    def _reset_argparse(self):
        self.argparse = ArgumentParser(add_help=False, exit_on_error=False)
        self.argparse.add_argument(
            "--help",
            "-h",
            action="store_true",
            default=False,
            required=False,
            help="show this help message and exit",
        )

    def _handle_help_call(self):
        if self.parse_args.help_strategy != "silent":
            self._print_usage(self.argparse, False)
        if self.parse_args.help_strategy == "print-and-exit":
            sys.exit(2)

    def _setup_argument(
        self,
        arg_name: str,
        arg_type: type,
        arg_default: Any,
        arg_required: bool,
        arg_help: Optional[str],
        arg_aliases: Optional[list[str]],
    ):
        if not arg_aliases:
            arg_aliases = []

        args = self._dispatch_argparse_key_type(
            arg_name,
            arg_type,
            arg_default,
            arg_required,
        )
        argparse_kwargs: dict[str, Any]
        argparse_kwargs = dict()

        if args.action and args.action in {"store_true", "store_false"}:
            argparse_kwargs["action"] = args.action
        else:
            argparse_kwargs["type"] = args.type
        argparse_kwargs["default"] = args.default
        argparse_kwargs["required"] = args.required
        if args.nargs:
            argparse_kwargs["nargs"] = "+"
        if args.choices:
            argparse_kwargs["choices"] = args.choices
        if arg_help:
            argparse_kwargs["help"] = arg_help

        if "action" not in argparse_kwargs:
            argparse_kwargs["metavar"] = (
                arg_type.__name__ if hasattr(arg_type, "__name__") else repr(arg_type)
            )

        self.argparse.add_argument("--" + args.name, *arg_aliases, **argparse_kwargs)

    def _dispatch_argparse_key_type(
        self, arg_name: str, arg_type: type, arg_default: Any, arg_required: bool
    ) -> _Argument:
        logger.debug(
            f"Dispatch: {arg_name} ({arg_type}) default={arg_default}, required={arg_required}"
        )

        if self.allow_dispatch_custom and arg_name in self.allow_custom:
            custom_func = self.allow_custom[arg_name]
            sign = inspect.signature(custom_func)

            if len(sign.parameters) != 1:
                param_names = "".join(
                    param.annotation for name, param in sign.parameters.items()
                )
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
                    f"{custom_type} as is input to {custom_func.__name__}"
                )
                inner = self._dispatch_argparse_key_type(
                    arg_name, custom_type, arg_default, arg_required
                )

            self._register_post_parse_type_conversion(arg_name, custom_func)
            return inner

        origin_arg_type = get_origin(arg_type)
        if arg_type == bool:
            if arg_default is not MISSING_ARG and not isinstance(arg_default, bool):
                raise ValueError(
                    f"Default value for {arg_name} is of type {type(arg_default)}, but should be bool"
                )

            arg_default = arg_default if arg_default is not None else False

            store_action = "store_true" if not arg_default else "store_false"
            return _Argument(
                arg_name,
                arg_type,
                arg_default,
                arg_required,
                nargs=False,
                action=store_action,
            )
        elif origin_arg_type and origin_arg_type in SEQUENCE_TYPES:
            inner_arg_type = get_args(arg_type)[0]
            inner = self._dispatch_argparse_key_type(
                arg_name, inner_arg_type, arg_default, arg_required
            )

            if origin_arg_type is not list:
                self._register_post_parse_type_conversion(arg_name, origin_arg_type)

            return _Argument(
                inner.name,
                inner.type,
                inner.default,
                inner.required,
                True,
            )
        elif origin_arg_type and origin_arg_type is Literal:
            literal_values = get_args(arg_type)
            inner_args = set(map(type, literal_values))
            if len(set(inner_args)) == 1:
                inner_arg_type = first(
                    inner_args,
                )
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
        elif origin_arg_type and origin_arg_type in {Union, UnionType}:
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
                    arg_name, inner_arg_type, arg_default, arg_required
                )
                return inner
            none_in_inner = NoneType in inner_arg_types

            if none_in_inner:
                raise NotImplementedError(inner_arg_types)
            inner_arg_types = tuple(
                self._dispatch_argparse_key_type(
                    arg_name, inner_arg_type, arg_default, arg_required
                )
                for inner_arg_type in inner_arg_types
            )
            if len(inner_arg_types) < 2:
                raise ValueError()

            inner_types = [inner.type for inner in inner_arg_types]

            def first_working_inner_type(inp):
                for inner_type in inner_types:
                    try:
                        return inner_type(inp)
                    except Exception:
                        continue
                raise ValueError(inp)

            first_inner = inner_arg_types[0]
            return _Argument(
                first_inner.name,
                first_working_inner_type,
                first_inner.default,
                first_inner.required,
                first_inner.nargs,
                first_inner.choices,
                first_inner.action,
            )
        elif origin_arg_type:
            inner_arg_types = get_args(arg_type)
            raise ValueError(
                "Unsupported origin type "
                + str(origin_arg_type)
                + " for type "
                + str(arg_type)
                + " "
                "with inner types " + str(inner_arg_types)
            )
        else:
            orig_arg_name = arg_name
            if arg_type in {Path, str} and orig_arg_name in self.allow_glob:
                self._register_post_parse_type_conversion(
                    orig_arg_name,
                    flatten,
                )

                return _Argument(
                    arg_name,
                    partial(glob_to_paths, func=arg_type),
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
