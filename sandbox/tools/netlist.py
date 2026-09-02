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

    `params` receives each match and returns the new tail as a mapping.
    """

    def swap(match: re.Match) -> str:
        tail = " ".join(
            f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}"
            for k, v in params(match).items()
        )
        return f"{match.group('head')} {tail}"

    return instances(model).sub(swap, text)
