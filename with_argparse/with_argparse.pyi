from typing import Callable, Protocol, Any, TypeVar, Literal, Optional, overload

from with_argparse.configure_argparse import WithArgparse, ParseArgs

T = TypeVar("T")

class FunctionWithSpecificReturnType(Protocol[T]):
    def __call__(self, *args, **kwargs) -> T: ...

class StrictArgParsedFunction(Protocol[T]):
    def __call__(self) -> T: ...

@overload
def with_dataclass(func: FunctionWithSpecificReturnType[T], /) -> StrictArgParsedFunction[T]:
    ...

@overload
def with_attrs(func: FunctionWithSpecificReturnType[T], /) -> StrictArgParsedFunction[T]:
    ...

@overload
def with_attrs(
    *,
    parse_args: ParseArgs | None = None,
    strict: Literal[True] = True,
) -> Callable[[FunctionWithSpecificReturnType[T]], StrictArgParsedFunction[T]]:
    ...

@overload
def with_dataclass(
    allow_glob: Optional[set[str]] = None,
    partial_parse: Optional[bool] = None,
    add_help: Optional[bool] = None,
    on_help: Optional[Callable[[WithArgparse], Any]] = None,
    partial_parse_pass_remaining_args: Optional[bool] = None,
    strict: Literal[True] = True,
) -> Callable[[FunctionWithSpecificReturnType[T]], StrictArgParsedFunction[T]]: ...
