from glob import glob
from pathlib import Path
from typing import Any, TypeVar, Callable


def flatten(input: list[list[Any]]) -> list[Any]:
    return [a for b in input for a in b]

T = TypeVar('T')

def glob_to_paths(inp: str, func: Callable[[str], T]) -> list[T]:
    return list(map(func, glob(inp)))
