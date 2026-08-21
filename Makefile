# Build entry point for SAR-ASIC.
#
# Everything here assumes the IIC-OSIC-TOOLS container, which supplies
# verilator, yosys, verible, cocotb, and the sky130A PDK. See README.md.
#
# `make` on its own prints help and changes nothing.

.DEFAULT_GOAL := help

PYTHON       ?= python
PYTEST       ?= $(PYTHON) -m pytest
RUFF         ?= ruff
YOSYS        ?= yosys
VERIBLE_FMT  ?= verible-verilog-format
VERIBLE_LINT ?= verible-verilog-lint

RTL_DIR   := hdl/rtl
REF_DIR   := hdl/reference
VERIF_DIR := hdl/verification
BUILD_DIR := build

RTL_SOURCES := $(shell find $(RTL_DIR) -name '*.v' 2>/dev/null)

# Top module for synthesis. Required by `make synth`.
TOP ?=

# pytest exits 5 when it collects nothing. During bring-up most directories are
# empty, so treat that as a warning rather than a failure -- but say so loudly,
# because a silent empty run looks identical to a passing one.
define run_pytest
	@$(PYTEST) $(1) $(PYTEST_ARGS); status=$$$$?; 	if [ $$$$status -eq 5 ]; then 		echo "WARNING: no tests collected in $(1)"; 	else 		exit $$$$status; 	fi
endef

## help: list available targets
help:
	@echo "SAR-ASIC targets:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
	@echo ""
	@echo "Flags:  WAVES=1 dumps FST into $(BUILD_DIR)/sim/<top>/"
	@echo "        TOP=<module> required by 'make synth'"

## format: rewrite Verilog and Python in canonical style
format:
	@if [ -n "$(RTL_SOURCES)" ]; then $(VERIBLE_FMT) --inplace $(RTL_SOURCES); fi
	$(RUFF) format .
	$(RUFF) check --fix .

## format-check: fail if anything is unformatted (CI uses this, never `format`)
format-check:
	@for f in $(RTL_SOURCES); do 		$(VERIBLE_FMT) $$$$f | diff -u $$$$f - || exit 1; 	done
	$(RUFF) format --check .

## lint: all linters
lint: lint-rtl lint-py

## lint-rtl: verilator --lint-only -Wall, plus verible style lint
lint-rtl:
	$(PYTHON) scripts/lint_rtl.py
	@if [ -n "$(RTL_SOURCES)" ]; then $(VERIBLE_LINT) $(RTL_SOURCES); fi

## lint-py: ruff
lint-py:
	$(RUFF) check .

## model: validate the Python golden models -- run this before any RTL exists
model:
	$(call run_pytest,$(REF_DIR))

## verify-unit: cocotb unit tests
verify-unit:
	$(call run_pytest,$(VERIF_DIR)/unit)

## verify-integration: cocotb integration tests
verify-integration:
	$(call run_pytest,$(VERIF_DIR)/integration)

## verify-system: full-converter tests (slow)
verify-system:
	$(call run_pytest,$(VERIF_DIR)/system)

## verify: model, then every verification level, in order
verify: model verify-unit verify-integration verify-system

## synth: yosys sanity check and cell-count estimate. NOT the shuttle result.
synth:
	@if [ -z "$(TOP)" ]; then echo "error: set TOP=<module>"; exit 1; fi
	@if [ -z "$(RTL_SOURCES)" ]; then echo "error: no .v files in $(RTL_DIR)"; exit 1; fi
	@echo "NOTE: estimate only. TinyTapeout's GDS action is authoritative."
	$(YOSYS) -p "read_verilog $(RTL_SOURCES); hierarchy -check -top $(TOP); 		proc; opt; synth -top $(TOP); stat"

## clean: remove generated output
clean:
	rm -rf $(BUILD_DIR)
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache

.PHONY: help format format-check lint lint-rtl lint-py model 	verify-unit verify-integration verify-system verify synth clean
