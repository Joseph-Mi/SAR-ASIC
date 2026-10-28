v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {sar_analog -- the analog tile, as the digital half sees it.} -600 -340 0 0 0.4 0.4 {}
T {Drawn: the comparator, the capacitor array and the phase generator.
Not yet drawn: the sampling and conversion switches. Their netlists are in
sim/analog.py and they arrive on the sheet as each one is laid out.
The ports below are the frozen interface (reference/interface.py) and are
declared whether or not anything is wired to them yet.} -600 -300 0 0 0.25 0.25 {}
T {bottom plates, waiting for their switches} -480 170 0 0 0.25 0.25 {}
N -30 -30 50 -30 {lab=vref}
N -30 -10 50 -10 {lab=cmp_clk}
N -30 10 50 10 {lab=vcm}
N -180 30 50 30 {lab=top}
N 350 -30 430 -30 {lab=vdd}
N 350 -10 430 -10 {lab=vss}
N 350 10 600 10 {lab=cmp_out}
N 350 30 600 30 {lab=cmp_out_n}
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
C {lab_pin.sym} -30 -30 0 0 {name=l0 lab=vref}
C {lab_pin.sym} -30 -10 0 0 {name=l1 lab=cmp_clk}
C {lab_pin.sym} -30 10 0 0 {name=l2 lab=vcm}
C {lab_pin.sym} -180 30 0 0 {name=l3 lab=top}
C {lab_pin.sym} 430 -30 2 0 {name=l4 lab=vdd}
C {lab_pin.sym} 430 -10 2 0 {name=l5 lab=vss}
C {phase_gen.sym} -330 -150 0 0 {name=Xphases}
C {lab_pin.sym} -480 -170 0 0 {name=lg0 lab=vdd}
C {lab_pin.sym} -480 -150 0 0 {name=lg1 lab=vss}
C {lab_pin.sym} -480 -130 0 0 {name=lg2 lab=sample}
C {lab_pin.sym} -180 -180 0 0 {name=lg3 lab=phi_top}
C {lab_pin.sym} -180 -160 0 0 {name=lg4 lab=phi_bot}
C {lab_pin.sym} -180 -140 0 0 {name=lg5 lab=phi_bot_n}
C {lab_pin.sym} -180 -120 0 0 {name=lg6 lab=phi_conv}
T {the phases, waiting for the switches they drive} -180 -100 0 0 0.25 0.25 {}
C {cap_array.sym} -330 30 0 0 {name=Xarray}
C {lab_pin.sym} -480 -70 0 0 {name=la0 lab=b0}
C {lab_pin.sym} -480 -50 0 0 {name=la1 lab=b1}
C {lab_pin.sym} -480 -30 0 0 {name=la2 lab=b2}
C {lab_pin.sym} -480 -10 0 0 {name=la3 lab=b3}
C {lab_pin.sym} -480 10 0 0 {name=la4 lab=b4}
C {lab_pin.sym} -480 30 0 0 {name=la5 lab=b5}
C {lab_pin.sym} -480 50 0 0 {name=la6 lab=b6}
C {lab_pin.sym} -480 70 0 0 {name=la7 lab=b7}
C {lab_pin.sym} -480 90 0 0 {name=la8 lab=b8}
C {lab_pin.sym} -480 110 0 0 {name=la9 lab=b9}
C {lab_pin.sym} -480 130 0 0 {name=la10 lab=bd}
