from glob import glob
from pathlib import Path
from typing import Any


def flatten(input: list[list[Any]]) -> list[Any]:
    return [a for b in input for a in b]


def glob_to_path_list(input: str) -> list[Path]:
    return list(map(Path, glob(input)))
