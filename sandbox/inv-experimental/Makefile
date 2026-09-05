MAGIC  ?= magic -dnull -noconsole
PYTHON ?= python3
CELL   ?= inv

.PHONY: all layout drc lvs pex sim clean

all: layout drc lvs pex sim

layout:
	$(MAGIC) gen_inv.tcl

drc:
	@$(MAGIC) drc_inv.tcl | sed -n '/DRC_TOTAL/,$$p'

lvs:
	sak-lvs.sh -s $(CELL).sch -l $(CELL).mag -c $(CELL)

pex:
	sak-pex.sh $(CELL)

sim:
	@$(PYTHON) characterize.py pex

clean:
	rm -rf $(CELL).magic.lvs $(CELL)_magic.spice
	rm -f *.ext *.spc *.res.ext *.nodes comp.out netgen.log *.lvs.report
	rm -f *.pex.spice *.pex.log
