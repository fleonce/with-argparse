from glob import glob
from typing import Any


def flatten(input: list[list[Any]]) -> list[Any]:
    return [a for b in input for a in b]


def glob_to_path_list(input: str, map_t: type = str) -> list[str]:
    return list(map(map_t, glob(input)))
