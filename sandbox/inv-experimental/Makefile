# Inverter layout: generate, check, compare against the schematic.
#
# The layout is a build product of gen_inv.tcl, not something edited by hand.
# Opening inv.mag in magic and saving will be overwritten by the next `make
# layout`; change the generator instead.

MAGIC ?= magic -dnull -noconsole
CELL  ?= inv

.PHONY: all layout drc lvs pex clean

all: layout drc lvs

## layout: build inv.mag and its device cells from nothing
layout:
	$(MAGIC) gen_inv.tcl

## drc: geometry rules, in a fresh process so the count reflects what is on disk
drc:
	@$(MAGIC) drc_inv.tcl | sed -n '/DRC_TOTAL/,$$p'

## lvs: does the layout match the schematic
lvs:
	sak-lvs.sh -s $(CELL).sch -l $(CELL).mag -c $(CELL)

## pex: extract parasitics into a netlist that can be simulated
##      Kept out of `all`: it re-extracts what lvs already did, and nothing
##      downstream consumes it until a testbench is pointed at it.
pex:
	sak-pex.sh $(CELL)

## clean: extraction and comparison products, never the sources
clean:
	rm -rf $(CELL).magic.lvs $(CELL)_magic.spice
	rm -f *.ext *.spc *.res.ext *.nodes comp.out netgen.log *.lvs.report
	rm -f *.pex.spice *.pex.log
