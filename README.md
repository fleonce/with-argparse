# with-argparse

`with-argparse` is a very simple and tiny package using `argparse.ArgumentParser` objects
to derive a CLI that is automatically applied to a function using type annotations. 
*Currently supports Python 3.10-11*.

### Supported features:

- Argument lists via `nargs=+`
- Argument choices via `typing.Literal[x, y, z]`
- Optional values and required arguments
- Boolean flags via presence or abscence of `--argument_name`
- Custom parse functions via `@with_argparse(arg_name=custom_fn)`
- Ignored values: `@with_argparse(ignore_keys={'arg_name'}`
- Nested type annotations such as `list[int]`
- Disabled mode: `with_argparse.no_argparse()` context manager

In order for this package to work, functions must receive an explicit type annotation.
The following type annotations are currently supported:

- `str, int, float, bool, ...`
- Types that have constructors that accept a single `str` as input
- `list[type]` and `set[type]`
- `Optional[type], type | None, Union[type, None]`,
- `Literal[type_val1, type_val2]`
- Custom types via custom parse functions (supplied via `kwarg` to the `@with_argparse` decorator.

### Example code

```python3
from typing import Optional
from with_argparse import with_argparse

def custom_parse_fn(inp: str) -> int:
    return 42 if inp == "yeah" else -1

@with_argparse(
    ignore_keys={"ignored_value"}, 
    complex_input=custom_parse_fn
)
def cli(
    theory_of_everything: int,
    complex_input: int,
    ignored_value: Optional[str] = None,
) -> int:
    print(ignored_value)
    return theory_of_everything * complex_input

cli(ignored_value="abc")
```

will generate the following CLI output when run:

```text
usage: --theory_of_everything THEORY_OF_EVERYTHING
                    [--complex_input COMPLEX_INPUT]
```

### Custom parse functions

Becomes increasingly useful when the target type `T` does not have a default constructor with a single `str` argument
or more complex logic is required to parse the desired type from a string input.

As it is not type correct to use functions as type annotations (it would work extracting those functions from there, 
however type checkers such as mypy will complain when doing so), one can specify custom parse functions
directly in the `@with_argparse()` decorator via a keyword argument named as the target parameter.

Say we have a complex function that does call some other functions before eventually returning the string in reverse:
```python

def func_a(a: str) -> str: ...
def func_b(b: str) -> str: ...

def custom_fn(inp: str):
    inp = func_a(inp)
    inp = func_b(inp)
    return str(reversed(inp))
```

Our custom function can also accept types differing from `str`, such as `int`.

We can then use this function to parse the input the following way in our dummy `cli` function:

```python
@with_argparse(complex_input=custom_fn)
def cli(complex_input: str) -> str:
    return complex_input
```

### Boolean values

For Boolean values, if the default specified is `True`, the CLI argument name is renamed to `--no_argname`,
such that the user must specify to *disable* the given argument. In any other case (`None, False`), the user must
specify `--arg_name` to set the Boolean argument to `True`,

The renaming of a parameter can be disabled by specifying its name in the set `ignore_mapping`, again in the 
`@with_argparse` decorator to the function.
