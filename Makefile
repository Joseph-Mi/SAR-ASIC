# Build entry point for SAR-ASIC.
#
# Everything here assumes the IIC-OSIC-TOOLS container, which supplies
# verilator, yosys, verible, cocotb, and the sky130A PDK. See README.md.
#
# `make` on its own prints help and changes nothing.

.DEFAULT_GOAL := help

# Native tool versions. Also sourced by CI.
include versions.env

PYTHON       ?= python
VERILATOR    ?= verilator
RUFF         ?= ruff
YOSYS        ?= yosys
VERIBLE_FMT  ?= verible-verilog-format
VERIBLE_LINT ?= verible-verilog-lint

# Container. DESIGNS is bind-mounted to /foss/designs, so it must be the PARENT
# of this repo -- that is what puts us at /foss/designs/$(DESIGN_NAME) inside.
# An exported DESIGNS in the environment wins, which is what you want if you also
# run the start scripts by hand.
OSIC_TOOLS_URL := https://github.com/iic-jku/iic-osic-tools.git
OSIC_TOOLS_DIR ?= $(abspath $(CURDIR)/../iic-osic-tools)
DESIGNS        ?= $(abspath $(CURDIR)/..)
DESIGN_NAME    := $(notdir $(CURDIR))
CONTAINER_NAME ?= iic-osic-tools_xvnc_uid_$(shell id -u)

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
	@grep -hE '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
	@echo ""
	@echo "Flags:  WAVES=1  dump FST into $(BUILD_DIR)/sim/<top>/"

## doctor: check host prerequisites -- run this first on a new machine
doctor:
	@command -v git >/dev/null || { echo "git not found -- see docs/environment.md"; exit 1; }
	@command -v docker >/dev/null || { echo "docker not found -- see docs/environment.md"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "docker daemon unreachable: is it running, and are you in the docker group? -- see docs/environment.md"; exit 1; }
	@[ -d "$(DESIGNS)/$(DESIGN_NAME)" ] || { echo "DESIGNS=$(DESIGNS) does not contain $(DESIGN_NAME); the container would mount an empty tree"; exit 1; }
	@echo "host OK -- DESIGNS=$(DESIGNS)"

# We read the helper scripts and never write them. A missing checkout is created
# at the pinned tag -- there is nothing there to clobber. An existing checkout is
# only ever *verified*: if it has drifted off the pin, say so and stop rather
# than moving someone else's working tree underneath them.
## osic-tools: ensure the helper scripts exist at the tag in versions.env
osic-tools: doctor
	@if [ ! -d "$(OSIC_TOOLS_DIR)/.git" ]; then \
	  echo "cloning iic-osic-tools at $(OSIC_TOOLS_TAG) ..."; \
	  git clone --quiet --branch "$(OSIC_TOOLS_TAG)" $(OSIC_TOOLS_URL) "$(OSIC_TOOLS_DIR)"; \
	fi
	@got=$$(cd "$(OSIC_TOOLS_DIR)" && git describe --tags --always --exact-match 2>/dev/null || echo "<no tag>"); \
	if [ "$$got" != "$(OSIC_TOOLS_TAG)" ]; then \
	  echo "iic-osic-tools is at $$got, but versions.env pins $(OSIC_TOOLS_TAG)."; \
	  echo "The start scripts and the image must match. Fix it yourself -- this"; \
	  echo "repo does not write to that checkout:"; \
	  echo "    git -C $(OSIC_TOOLS_DIR) fetch --tags && git -C $(OSIC_TOOLS_DIR) checkout $(OSIC_TOOLS_TAG)"; \
	  exit 1; \
	fi
	@echo "iic-osic-tools $(OSIC_TOOLS_TAG) at $(OSIC_TOOLS_DIR)"

# start_vnc.sh prompts to STOP a container that is already running, so check
# first rather than letting `make shell` offer to kill the session it needs.
## container: start the pinned container (first run pulls ~20 GB)
container: osic-tools
	@if [ -n "$$(docker ps -q -f name=$(CONTAINER_NAME))" ]; then \
	  echo "already running -- VNC at http://localhost/?password=abc123"; \
	else \
	  DESIGNS="$(DESIGNS)" DOCKER_TAG="$(OSIC_TOOLS_TAG)" "$(OSIC_TOOLS_DIR)/start_vnc.sh"; \
	fi

## shell: bash inside the running container, at this design
shell: container
	@docker exec -it -w /foss/designs/$(DESIGN_NAME) $(CONTAINER_NAME) bash

## tool-versions: print what is actually installed
tool-versions:
	@$(PYTHON) --version
	@$(VERILATOR) --version
	@$(YOSYS) -V
	@$(VERIBLE_FMT) --version | head -1
	@$(RUFF) --version
	@$(PYTHON) -c "import cocotb; print('cocotb', cocotb.__version__)"
	@$(PYTHON) -c "import pytest; print('pytest', pytest.__version__)"

## tool-manifest: record every tool version into docs/tool-manifest.txt
tool-manifest:
	@OSIC_TOOLS_TAG="$(OSIC_TOOLS_TAG)" sh scripts/tool-manifest.sh > docs/tool-manifest.txt
	@echo "wrote docs/tool-manifest.txt"

## check-tools: fail unless installed versions match versions.env
check-tools:
	@got=$$($(VERILATOR) --version | awk '{print $$2}'); [ "$$got" = "$(VERILATOR_VERSION)" ] || { echo "verilator: want $(VERILATOR_VERSION), got $$got"; exit 1; }
	@got=$$($(YOSYS) -V | awk '{print $$2}'); [ "$$got" = "$(YOSYS_VERSION)" ] || { echo "yosys: want $(YOSYS_VERSION), got $$got"; exit 1; }
	@$(VERIBLE_FMT) --version | grep -qF '$(VERIBLE_VERSION)' || { echo "verible: want $(VERIBLE_VERSION), got $$($(VERIBLE_FMT) --version | head -1)"; exit 1; }
	@echo "native tools match versions.env"

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

.PHONY: help doctor osic-tools container shell tool-versions tool-manifest check-tools format format-check lint lint-rtl lint-py model verify-unit verify-integration verify-system verify clean
