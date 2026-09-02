"""Rewriting device instances in a SPICE netlist."""

from __future__ import annotations

import re


def instances(model: str) -> re.Pattern:
    """Instance lines calling a model matching `model`.

    `head` captures the reference, nodes and model name -- everything a caller
    must preserve. Node count is not fixed, so this holds for any device.
    """
    return re.compile(rf"^(?P<head>X\S+\s+.+?\s+(?P<model>{model}))(?:\s.*)?$", re.M)


def restamp(text: str, model: str, params) -> str:
    """Replace the parameter tail of every instance calling `model`.

    `params` receives each match and returns the new tail as a mapping. The
    tail is replaced whole, so the mapping carries every parameter the instance
    is to keep.

    Matching nothing raises. A substitution that quietly changed nothing would
    hand back the original geometry under the caller's labels, which reads as a
    result rather than as a failure.
    """

    def swap(match: re.Match) -> str:
        tail = " ".join(
            f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}"
            for k, v in params(match).items()
        )
        return f"{match.group('head')} {tail}"

    stamped, count = instances(model).subn(swap, text)
    if not count:
        raise ValueError(f"no instance of {model} to restamp")
    return stamped
