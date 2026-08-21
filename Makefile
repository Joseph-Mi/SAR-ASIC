# Build entry point for SAR-ASIC.
#
# Everything here assumes the IIC-OSIC-TOOLS container, which supplies
# verilator, yosys, verible, cocotb, and the sky130A PDK. See README.md.
#
# `make` on its own prints help and changes nothing.

.DEFAULT_GOAL := help

PYTHON       ?= python
VERILATOR    ?= verilator
RUFF         ?= ruff
YOSYS        ?= yosys
VERIBLE_FMT  ?= verible-verilog-format
VERIBLE_LINT ?= verible-verilog-lint

RTL_DIR   := hdl/rtl
REF_DIR   := hdl/reference
VERIF_DIR := hdl/verification
BUILD_DIR := build
WAIVERS   := hdl/lint/waivers.vlt

RTL_SOURCES := $(shell find $(RTL_DIR) -name '*.v' 2>/dev/null)
RTL_SEARCH  := $(addprefix -y ,$(sort $(dir $(RTL_SOURCES))))

# -y lets Verilator resolve submodules by filename, so each file is linted
# standalone as its own top and uninstantiated modules still get checked.
# This relies on file name matching module name.
VERILATOR_LINT := $(VERILATOR) --lint-only -Wall --timescale 1ns/1ps $(RTL_SEARCH) $(WAIVERS)

YOSYS_CHECK := read_verilog $(RTL_SOURCES); hierarchy -check -auto-top; proc; opt_clean; check -assert

# pytest exits 5 when it collects nothing. Empty directories are normal during
# bring-up, so that is a warning; any other non-zero status is a real failure.
ALLOW_EMPTY = s=$$?; if [ $$s -eq 5 ]; then echo "WARNING: no tests collected"; else exit $$s; fi

## help: list available targets
help:
	@echo "SAR-ASIC targets:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
	@echo ""
	@echo "Flags:  WAVES=1  dump FST into $(BUILD_DIR)/sim/<top>/"

## check-tools: print the version of every tool this Makefile depends on
check-tools:
	@echo "--- expected: docs/tool-versions.md ---"
	@$(PYTHON) --version
	@$(VERILATOR) --version
	@$(YOSYS) -V
	@$(VERIBLE_FMT) --version | head -1
	@$(RUFF) --version
	@$(PYTHON) -c "import cocotb; print('cocotb', cocotb.__version__)"
	@$(PYTHON) -c "import pytest; print('pytest', pytest.__version__)"

## format: rewrite Verilog and Python in canonical style
format:
	@if [ -n "$(RTL_SOURCES)" ]; then $(VERIBLE_FMT) --inplace $(RTL_SOURCES); fi
	$(RUFF) format .
	$(RUFF) check --fix .

## format-check: fail if anything is unformatted (CI uses this, never `format`)
format-check:
	@for f in $(RTL_SOURCES); do $(VERIBLE_FMT) $$f | diff -u $$f - || exit 1; done
	$(RUFF) format --check .

## lint: every linter
lint: lint-rtl lint-py

## lint-rtl: verilator lint, verible style lint, yosys structural check
lint-rtl:
	@for f in $(RTL_SOURCES); do echo "lint $$f"; $(VERILATOR_LINT) --top-module $$(basename $$f .v) $$f || exit 1; done
	@if [ -n "$(RTL_SOURCES)" ]; then $(VERIBLE_LINT) $(RTL_SOURCES); fi
	@if [ -n "$(RTL_SOURCES)" ]; then $(YOSYS) -qp "$(YOSYS_CHECK)"; fi

## lint-py: ruff
lint-py:
	$(RUFF) check .

## model: validate the Python golden models -- run before any RTL exists
model:
	@$(PYTHON) -m pytest $(REF_DIR) $(PYTEST_ARGS); $(ALLOW_EMPTY)

## verify-unit: cocotb unit tests
verify-unit:
	@$(PYTHON) -m pytest $(VERIF_DIR)/unit $(PYTEST_ARGS); $(ALLOW_EMPTY)

## verify-integration: cocotb integration tests
verify-integration:
	@$(PYTHON) -m pytest $(VERIF_DIR)/integration $(PYTEST_ARGS); $(ALLOW_EMPTY)

## verify-system: full-converter tests (slow)
verify-system:
	@$(PYTHON) -m pytest $(VERIF_DIR)/system $(PYTEST_ARGS); $(ALLOW_EMPTY)

## verify: model, then every verification level, in order
verify: model verify-unit verify-integration verify-system

## clean: remove generated output
clean:
	rm -rf $(BUILD_DIR) .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

.PHONY: help check-tools format format-check lint lint-rtl lint-py model verify-unit verify-integration verify-system verify clean
