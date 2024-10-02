import typing
import warnings
from dataclasses import dataclass
from email.policy import default
from types import NoneType
from typing import Any, Set, List, get_origin, get_args, Union, Literal, Optional, Sequence, TypeVar, Iterable
from typing_extensions import reveal_type

SET_TYPES = {set, Set}
LIST_TYPES = {list, List}
SEQUENCE_TYPES = SET_TYPES | LIST_TYPES

_T = TypeVar("_T")

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
    type: type
    default: Any
    required: bool
    nargs: bool
    choices: Optional[Sequence[Any]] = None


class WithArgparse:
    _ignore_rename_sequences: set[str]

    def __init__(self):
        super().__init__()
        self._ignore_rename_sequences = set()


    def _register_mapping(self): ...

    def _register_post_parse_type_conversion(self): ...

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
        ...

    def _dispatch_argparse_key_type(
        self,
        arg_name: str,
        arg_type: type,
        arg_default: Any,
        arg_required: bool
    ) -> _Argument:
        pass
        origin_arg_type = get_origin(arg_type)
        if (
            origin_arg_type
            and origin_arg_type in SEQUENCE_TYPES
            and arg_name not in self._ignore_rename_sequences
            and arg_name.endswith("s")
        ):
            arg_name = self._register_substitution(arg_name, arg_name[:-1])

        if arg_type == bool:
            if arg_default is not None and not isinstance(arg_default, bool):
                raise ValueError(f"Default value for {arg_name} is of type {type(arg_default)}, but should be bool")

            arg_default = arg_default if arg_default is not None else False
            if arg_default:
                arg_name = self._register_substitution(arg_name, "no_" + arg_name)
            return _Argument(
                arg_name,
                arg_type,
                arg_default,
                arg_required,
                nargs=False,
            )
        elif (
            origin_arg_type
            and origin_arg_type in SEQUENCE_TYPES
        ):
            inner_arg_type = get_args(origin_arg_type)[0]
            inner = self._dispatch_argparse_key_type(
                arg_name,
                inner_arg_type,
                arg_default,
                arg_required
            )

            if origin_arg_type is not list:
                self._register_post_parse_type_conversion()

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
                # Optional[inner_type]
                non_none_inner_arg_types = set(inner_arg_types) - {NoneType}
                inner_arg_type = first(non_none_inner_arg_types)
                # reveal_type(inner_arg_type)
                if arg_default is not None:
                    warnings.warn(
                        f"Argument {arg_name} has type {arg_type} but cannot be None, "
                        f"got {arg_default} for default"
                    )
                inner = self._dispatch_argparse_key_type(
                    arg_name,
                    inner_arg_type,
                    arg_default,
                    arg_required
                )
                return inner
            raise NotImplementedError
        elif origin_arg_type:
            inner_args = get_args(arg_type)
            raise ValueError(
                "Unsupported origin type " + str(origin_arg_type) + " for type " + str(arg_type) + " "
                "with inner types " + str(inner_args)
            )


cls = WithArgparse()
a = cls._dispatch_argparse_key_type("test", Optional[list[int]], None, True)
print(a)
b = cls._dispatch_argparse_key_type("test", Optional[list[int]], 123, True)
print(b)
