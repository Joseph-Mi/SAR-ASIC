"""The repository's layers, and the one direction imports may run between them.

Contract: each layer may import only the layers beneath it. A module name is
the whole of its identity -- every layer shares one import path -- so no two
modules may share a name, and none may take a name the standard library has.
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
PYPROJECT = REPO / "pyproject.toml"

#: The linter's list of names it treats as ours. Read with a pattern rather than
#: with the standard library's TOML parser, which arrived after the Python
#: version the linter is configured to target: importing it here would claim a
#: newer floor than the configuration does.
FIRST_PARTY = re.compile(r"known-first-party\s*=\s*\[(?P<names>[^]]*)\]")
QUOTED = re.compile(r'"([^"]+)"')

#: Each layer, bottom first, with the layers it may import. A layer's tests
#: sit with it and follow its rule.
LAYERS = {
    "tech": set(),
    "reference": {"tech"},
    "model": {"tech", "reference"},
    "studies": {"tech", "reference", "model"},
    "sim": {"tech", "reference", "model"},
    "hdl/verification": {"tech", "reference", "model", "sim"},
}


def layer_of(path: str) -> str | None:
    """The layer a tracked file belongs to, or None when it is in none."""
    return next((name for name in LAYERS if path.startswith(name + "/")), None)


def all_sources() -> list[str]:
    """Every Python file git would keep, whatever directory it sits in.

    Files not yet added count. A module is at its most dangerous before it is
    committed: that is when nothing has been told about it, and when the linter
    complains about the files importing it rather than about the omission.
    """
    return subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()


def tracked_sources() -> list[str]:
    """Those of them that belong to a layer."""
    return [p for p in all_sources() if layer_of(p)]


def modules() -> dict[str, list[str]]:
    """Every importable module name, with the files that define it. Tests are
    not imported by anything, so they are not modules here."""
    found: dict[str, list[str]] = {}
    for path in tracked_sources():
        parts = pathlib.PurePath(path)
        if "tests" in parts.parts:
            continue
        name = parts.parent.name if parts.name == "__init__.py" else parts.stem
        found.setdefault(name, []).append(path)
    return found


def imports(path: str) -> set[str]:
    tree = ast.parse((REPO / path).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


def test_every_import_runs_down_the_layers():
    home = {name: layer_of(paths[0]) for name, paths in modules().items()}
    wrong = []
    for path in tracked_sources():
        layer = layer_of(path)
        for name in imports(path):
            target = home.get(name)
            if target and target != layer and target not in LAYERS[layer]:
                wrong.append(f"{path} ({layer}) imports {name} ({target})")
    assert not wrong, "imports against the layers:\n" + "\n".join(sorted(wrong))


def test_no_two_modules_share_a_name():
    shared = {name: paths for name, paths in modules().items() if len(paths) > 1}
    assert not shared, f"modules sharing a name: {shared}"


def test_no_module_takes_a_standard_library_name():
    taken = sorted(set(modules()) & sys.stdlib_module_names)
    assert not taken, f"modules shadowing the standard library: {taken}"


def first_party() -> set[str]:
    """The names the linter has been told are ours."""
    found = FIRST_PARTY.search(PYPROJECT.read_text())
    assert found, "the linter declares no first-party names"
    return set(QUOTED.findall(found["names"]))


def every_module() -> set[str]:
    """Every module name in the repository, whatever directory it sits in.

    Wider than `modules()`, which answers a question about the layers. The
    linter classifies an import by its name alone, so a module outside the
    layers -- the sandbox has its own -- counts here just as much.
    """
    names = set()
    for path in all_sources():
        parts = pathlib.PurePath(path)
        names.add(parts.parent.name if parts.name == "__init__.py" else parts.stem)
    return names


def test_the_linter_knows_every_module_we_import_is_ours():
    """A name the linter has not been told about is sorted into the third-party
    block, so every file importing it fails the import-order check -- and the
    complaint points at the import, not at the list that is missing it."""
    ours = every_module()
    imported = {name for path in all_sources() for name in imports(path) if name in ours}
    missing = sorted(imported - first_party())
    assert not missing, f"names the linter does not know are ours: {missing}"
