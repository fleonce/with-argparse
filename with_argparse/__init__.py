from .disable_argparse import no_argparse
from .main import with_attrs, no_argparse, partial_argparse, script_argparse

with_argparse = with_attrs
with_dataclass = with_attrs

__all__ = ["with_argparse", "no_argparse", "with_dataclass", "script_argparse", "with_attrs", "partial_argparse"]
