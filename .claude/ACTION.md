# CLAUDE.md

Operating instructions for Claude Code in this repo. This file is not
documentation: `README.md` describes the repo, `STYLE.md` holds the coding
rules, `docs/` holds specs and design notes. If a thing belongs in one of
those, it does not belong here.

## The order of work is a gate

Golden model, then tests, then RTL. If asked to write RTL for a block whose
model is missing from `hdl/reference/`, or whose tests do not yet pass against
that model, stop and write the missing piece first. Say that this is what you
are doing. `STYLE.md` explains why the order exists; do not relitigate it.

The golden model is never adjusted to make RTL pass.

## Commands

`make` is the entry point and `make` alone lists the targets. Reach for a target
rather than calling verilator, cocotb, yosys, or ruff directly — the targets
carry the flags, paths, and version checks, and invoking the tool by hand
silently skips them.

The toolchain is the IIC-OSIC-TOOLS container. On a bare host checkout the
tools are not on `PATH` and the suite cannot run. A `command not found` from a
build target is the environment, not the code: report it, do not install tools,
switch simulators, or rewrite the target to route around it.

Nothing under `build/` is edited or committed. It is generated.

## Nothing gets written twice

Tool versions live in `versions.env`. Python pins live in `requirements.txt`.
Design constants live in one place and are imported or generated across the
Python/Verilog boundary. Before typing a number, check whether it already
exists somewhere — if it does, read it, do not copy it. A value that appears in
two files is two values that will diverge.

This applies to prose as much as to code. Do not restate README or STYLE
content in a new file; name the source instead.

## Comments

`STYLE.md` is strict and it governs everything written here: nothing that
restates the code, no pointers from one source file to another, nothing that
goes stale on its own. Read that section before writing comments, not after a
review asks you to delete them.

That no-cross-file rule is about *source comments*. Documents may name other
documents — by name, never by line number.

## Keeping this file honest

Short and behavioral. It says what to do and what not to do; it does not
explain the design or duplicate the layout table. Anything copied here from
README, STYLE, or docs drifts out of sync with its source and is worse than
nothing, because it will be trusted.
