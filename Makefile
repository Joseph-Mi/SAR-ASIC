# Build entry point for SAR-ASIC.
#
# The IIC-OSIC-TOOLS container supplies verilator, yosys, verible, cocotb, and
# the sky130A PDK. See README.md.
#
# The container is a DOOR, not a build dependency. Only `container` and `shell`
# reach for it (via `osic-tools` -> `doctor`); every digital target -- model,
# lint, format, verify -- runs against whatever is on PATH. That is why CI runs
# them with no container at all, and why a digital-only contributor never needs
# Docker or the helper repo. Keep it that way: do not add `doctor` or
# `osic-tools` as a prerequisite of anything below.
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
VERIBLE_LINT_FLAGS ?= --rules_config=hdl/lint/verible.rules

# Container. DESIGNS is bind-mounted to /foss/designs, so it must be the PARENT
# of this repo -- that is what puts us at /foss/designs/$(DESIGN_NAME) inside.
# An exported DESIGNS in the environment wins, which is what you want if you also
# run the start scripts by hand.
# OSIC_TOOLS_DIR assumes a sibling checkout but is an override: point it
# anywhere with `make container OSIC_TOOLS_DIR=/path/to/iic-osic-tools`, or
# export it. Nothing else in this file depends on that layout.
OSIC_TOOLS_URL   := https://github.com/iic-jku/iic-osic-tools.git
OSIC_TOOLS_DIR   ?= $(abspath $(CURDIR)/../iic-osic-tools)
OSIC_START_SCRIPT = $(OSIC_TOOLS_DIR)/start_vnc.sh
DESIGNS        ?= $(abspath $(CURDIR)/..)
DESIGN_NAME    := $(notdir $(CURDIR))
CONTAINER_NAME ?= iic-osic-tools_xvnc_uid_$(shell id -u)

# The container sources exactly one fixed path at shell start, and it lives
# outside any repo. So $(DESIGNS)/.designinit is reduced to a shim that sources
# pdk.env from this repo: the settings stay under git, reviewable and visible to
# anyone who clones, and the out-of-repo file never needs editing again.
# noVNC reads the password from the query string, so the URL can be clicked
# straight through. Set OPEN=0 to print it without launching a browser.
VNC_PW          ?= abc123
OPEN            ?= 1
DESIGNINIT      := $(DESIGNS)/.designinit
DESIGNINIT_MARK := managed by make designinit

RTL_DIR   := hdl/rtl
REF_DIR   := hdl/reference
MODEL_DIR := model
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
	@[ -r "$(CURDIR)/pdk.env" ] || { echo "pdk.env is missing from this repo"; exit 1; }
	@grep -qsF '$(DESIGNINIT_MARK)' "$(DESIGNINIT)" || { \
	  echo "$(DESIGNINIT) does not source $(DESIGN_NAME)/pdk.env."; \
	  echo "The image defaults to PDK=ihp-sg13g2, so magic, ngspice and KLayout"; \
	  echo "would silently load the wrong technology and report no error."; \
	  echo "Fix with:  make designinit"; \
	  exit 1; \
	}
	@echo "host OK -- DESIGNS=$(DESIGNS), PDK from $(DESIGN_NAME)/pdk.env"

# We read the helper scripts and never write them. A missing checkout is created
# at the pinned tag -- there is nothing there to clobber. An existing checkout is
# only ever *verified*: if it has drifted off the pin, say so and stop rather
# than moving someone else's working tree underneath them.
# Writes one file outside the repo, and only that file: a shim with no settings
# in it. Anything it does not recognise as its own is left alone rather than
# overwritten -- the designs directory is shared with sibling projects.
## designinit: point the container's startup hook at pdk.env (idempotent)
designinit:
	@if [ -e "$(DESIGNINIT)" ] && ! grep -qsF '$(DESIGNINIT_MARK)' "$(DESIGNINIT)"; then \
	  echo "$(DESIGNINIT) exists and was not written by this repo."; \
	  echo "Refusing to overwrite it. Add this line to it yourself:"; \
	  echo '    [ -r "$$DESIGNS/$(DESIGN_NAME)/pdk.env" ] && . "$$DESIGNS/$(DESIGN_NAME)/pdk.env"'; \
	  exit 1; \
	fi
	@{ \
	  printf '%s\n' '# $(DESIGN_NAME) PDK hook -- $(DESIGNINIT_MARK). Do not edit.'; \
	  printf '%s\n' '# Settings live in $(DESIGN_NAME)/pdk.env, under git.'; \
	  printf '%s\n' '[ -r "$$DESIGNS/$(DESIGN_NAME)/pdk.env" ] && . "$$DESIGNS/$(DESIGN_NAME)/pdk.env"'; \
	} > "$(DESIGNINIT)"
	@echo "$(DESIGNINIT) -> $(DESIGN_NAME)/pdk.env"

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

# start_vnc.sh is interactive for both an already-running container ("press s to
# stop") and an exited one ("press s to start"), and in the exited case it can
# return 0 with nothing running. Handle both states here so restarting is one
# non-interactive command, and only fall through to the script to CREATE a
# container that does not exist yet.
## container: start the pinned container (first run pulls ~20 GB)
container: osic-tools
	@[ -x "$(OSIC_START_SCRIPT)" ] || { \
	  echo "$(OSIC_START_SCRIPT) is missing or not executable."; \
	  echo "Upstream moved it, or OSIC_TOOLS_DIR points somewhere wrong."; \
	  echo "Override with: make container OSIC_TOOLS_DIR=/path/to/iic-osic-tools"; \
	  exit 1; \
	}
	@if [ -n "$$(docker ps -q -f name=$(CONTAINER_NAME))" ]; then \
	  echo "already running"; \
	elif [ -n "$$(docker ps -aq -f name=$(CONTAINER_NAME))" ]; then \
	  echo "container exists but is stopped -- starting it"; \
	  docker start $(CONTAINER_NAME) >/dev/null; \
	  sleep 3; \
	else \
	  DESIGNS="$(DESIGNS)" DOCKER_TAG="$(OSIC_TOOLS_TAG)" "$(OSIC_START_SCRIPT)"; \
	fi
	@port=$$(docker port $(CONTAINER_NAME) 80 2>/dev/null | head -1 | sed 's/.*://'); \
	if [ -z "$$port" ]; then \
	  echo "container is up but port 80 is not published; VNC unavailable"; \
	else \
	  if [ "$$port" = "80" ]; then host=localhost; else host=localhost:$$port; fi; \
	  url="http://$$host/?password=$(VNC_PW)"; \
	  echo "VNC: $$url"; \
	  if [ "$(OPEN)" != "0" ]; then \
	    if command -v wslview >/dev/null 2>&1; then wslview "$$url" >/dev/null 2>&1 || true; \
	    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$$url" >/dev/null 2>&1 || true; \
	    elif command -v explorer.exe >/dev/null 2>&1; then explorer.exe "$$url" >/dev/null 2>&1 || true; \
	    else echo "(no browser opener found -- open the URL above yourself)"; fi; \
	  fi; \
	fi

## shell: bash inside the running container, at this design
shell: container
	@[ -n "$$(docker ps -q -f name=$(CONTAINER_NAME))" ] || { \
	  echo "$(CONTAINER_NAME) is not running."; \
	  echo "start_vnc.sh offers to start/remove an exited container and exits 0"; \
	  echo "if you decline, so re-run: make container"; \
	  exit 1; \
	}
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
	@tmp=$$(mktemp) && \
	  OSIC_TOOLS_TAG="$(OSIC_TOOLS_TAG)" sh scripts/tool-manifest.sh > "$$tmp" && \
	  mv "$$tmp" docs/tool-manifest.txt || { rm -f "$$tmp"; exit 1; }
	@echo "wrote docs/tool-manifest.txt"

# Yosys appends build metadata after a '+', so a source build of a release
# tarball and the image's build of the same release report different strings.
# That suffix describes the build, not the release, and the pin names the
# release -- so compare the part before the '+'.
## check-tools: fail unless installed versions match versions.env
check-tools:
	@got=$$($(VERILATOR) --version | awk '{print $$2}'); [ "$$got" = "$(VERILATOR_VERSION)" ] || { echo "verilator: want $(VERILATOR_VERSION), got $$got"; exit 1; }
	@got=$$($(YOSYS) -V | awk '{print $$2}' | cut -d+ -f1); [ "$$got" = "$(YOSYS_VERSION)" ] || { echo "yosys: want $(YOSYS_VERSION), got $$got"; exit 1; }
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
	@if [ -n "$(RTL_SOURCES)" ]; then $(VERIBLE_LINT) $(VERIBLE_LINT_FLAGS) $(RTL_SOURCES); fi
	@if [ -n "$(RTL_SOURCES)" ]; then $(YOSYS) -qp "$(YOSYS_CHECK)"; fi

## lint-py: ruff
lint-py:
	$(RUFF) check .

## model: validate the golden model and the mismatch study -- before any RTL
model:
	@$(PYTHON) -m pytest $(REF_DIR) $(MODEL_DIR) $(PYTEST_ARGS); $(ALLOW_EMPTY)

## study: regenerate the mismatch sweep artifact -- commit the diff
## 	ARGS="--gradient 0.01 --out build/model/grad.txt" for an exploratory run
study:
	@PYTHONPATH=$(REF_DIR):$(MODEL_DIR) $(PYTHON) $(MODEL_DIR)/yield_study.py $(ARGS)

## noise: regenerate the comparator noise artifact -- commit the diff
noise:
	@PYTHONPATH=$(REF_DIR):$(MODEL_DIR) $(PYTHON) $(MODEL_DIR)/noise_study.py $(ARGS)

## plots: draw the committed sweep into build/model/
plots:
	@PYTHONPATH=$(REF_DIR):$(MODEL_DIR) $(PYTHON) $(MODEL_DIR)/plots.py

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

.PHONY: noise help doctor designinit osic-tools container shell tool-versions tool-manifest check-tools format format-check lint lint-rtl lint-py model study plots verify-unit verify-integration verify-system verify clean
