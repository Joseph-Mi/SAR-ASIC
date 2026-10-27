v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {sar_analog -- the analog tile, as the digital half sees it.} -600 -340 0 0 0.4 0.4 {}
T {Drawn: the comparator. Not yet drawn: the capacitor array, the sampling
and conversion switches, and the phase generator. Their netlists are in
sim/analog.py and they arrive on the sheet as each one is laid out.
The ports below are the frozen interface (reference/interface.py) and are
declared whether or not anything is wired to them yet.} -600 -300 0 0 0.25 0.25 {}
C {ipin.sym} -600 -220 0 0 {name=p1 lab=dac_b[9:0]}
C {ipin.sym} -600 -180 0 0 {name=p2 lab=sample}
C {ipin.sym} -600 -140 0 0 {name=p3 lab=cmp_clk}
C {ipin.sym} -600 -100 0 0 {name=p4 lab=force_en}
C {ipin.sym} -600 -60 0 0 {name=p5 lab=force_hi}
C {ipin.sym} -600 -20 0 0 {name=p6 lab=vin}
C {ipin.sym} -600 20 0 0 {name=p7 lab=vref}
C {ipin.sym} -600 60 0 0 {name=p12 lab=vcm}
C {iopin.sym} -600 100 0 0 {name=p10 lab=vdd}
C {iopin.sym} -600 140 0 0 {name=p11 lab=vss}
C {opin.sym} 600 10 0 0 {name=p8 lab=cmp_out}
C {opin.sym} 600 30 0 0 {name=p9 lab=cmp_out_n}
C {strongarm.sym} 200 0 0 0 {name=Xcmp}
N 50 -30 -30 -30 {}
N 50 -10 -30 -10 {}
N 50 10 -30 10 {}
N 50 30 -180 30 {}
N 350 -30 430 -30 {}
N 350 -10 430 -10 {}
N 350 10 600 10 {}
N 350 30 600 30 {}
C {lab_pin.sym} -30 -30 0 0 {name=l0 lab=vref}
C {lab_pin.sym} -30 -10 0 0 {name=l1 lab=cmp_clk}
C {lab_pin.sym} -30 10 0 0 {name=l2 lab=vcm}
C {lab_pin.sym} -180 30 0 0 {name=l3 lab=top}
C {lab_pin.sym} 430 -30 0 0 {name=l4 lab=vdd}
C {lab_pin.sym} 430 -10 0 0 {name=l5 lab=vss}
T {the array's top plate} -180 60 0 0 0.25 0.25 {}
