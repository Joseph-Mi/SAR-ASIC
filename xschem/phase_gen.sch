v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {phase_gen -- three switch phases from one wire, each able to change
only once the phase it must follow has finished changing (DD-11).} -260 -240 0 0 0.4 0.4 {}
T {A logic sheet: every gate is a stack, and the lines between gates are carried by
name. What matters here is which line each gate watches, which the names say.
The arrangement is sim/phase_gen.py; the circuit is sim/analog.py, netlisted back
and compared element by element by sim/tests/test_phase_gen.py.} -260 -180 0 0 0.25 0.25 {}
T {the top switch's line: it follows sample} -260 -300 0 0 0.25 0.25 {}
N 20 0 20 0 {}
C {lab_pin.sym} 20 0 0 0 {name=l0 lab=btop_s0}
C {sky130_fd_pr/pfet_01v8.sym} 0 -100 0 0 {name=btop0p W=1 L=0.15 nf=1 mult=1 m=1}
N 20.0 -70.0 20 0 {}
C {lab_pin.sym} -20 -100 0 0 {name=l1 lab=sample}
C {lab_pin.sym} 20 -130 0 0 {name=l2 lab=vdd}
C {lab_pin.sym} 20 -100 0 0 {name=l3 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 100 0 0 {name=btop0n W=0.5 L=0.15 nf=1 mult=1 m=1}
N 20.0 70.0 20 0 {}
C {lab_pin.sym} -20 100 0 0 {name=l4 lab=sample}
C {lab_pin.sym} 20 130 0 0 {name=l5 lab=vss}
C {lab_pin.sym} 20 100 0 0 {name=l6 lab=vss}
N 120 0 120 0 {}
C {lab_pin.sym} 120 0 0 0 {name=l7 lab=phi_top}
C {sky130_fd_pr/pfet_01v8.sym} 100 -100 0 0 {name=btop1p W=4 L=0.15 nf=1 mult=1 m=1}
N 120.0 -70.0 120 0 {}
C {lab_pin.sym} 80 -100 0 0 {name=l8 lab=btop_s0}
C {lab_pin.sym} 120 -130 0 0 {name=l9 lab=vdd}
C {lab_pin.sym} 120 -100 0 0 {name=l10 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 100 100 0 0 {name=btop1n W=2 L=0.15 nf=1 mult=1 m=1}
N 120.0 70.0 120 0 {}
C {lab_pin.sym} 80 100 0 0 {name=l11 lab=btop_s0}
C {lab_pin.sym} 120 130 0 0 {name=l12 lab=vss}
C {lab_pin.sym} 120 100 0 0 {name=l13 lab=vss}
N 220 0 220 0 {}
C {lab_pin.sym} 220 0 0 0 {name=l14 lab=stop_lo}
C {sky130_fd_pr/pfet_01v8.sym} 200 -100 0 0 {name=stopsp W=0.42 L=1 nf=1 mult=1 m=1}
N 220.0 -70.0 220 0 {}
C {lab_pin.sym} 180 -100 0 0 {name=l15 lab=phi_top}
C {lab_pin.sym} 220 -130 0 0 {name=l16 lab=vdd}
C {lab_pin.sym} 220 -100 0 0 {name=l17 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 200 100 0 0 {name=stopsn W=2 L=0.15 nf=1 mult=1 m=1}
N 220.0 70.0 220 0 {}
C {lab_pin.sym} 180 100 0 0 {name=l18 lab=phi_top}
C {lab_pin.sym} 220 130 0 0 {name=l19 lab=vss}
C {lab_pin.sym} 220 100 0 0 {name=l20 lab=vss}
N 320 0 320 0 {}
C {lab_pin.sym} 320 0 0 0 {name=l21 lab=top_on}
C {sky130_fd_pr/pfet_01v8.sym} 300 -100 0 0 {name=stoprp W=1 L=0.15 nf=1 mult=1 m=1}
N 320.0 -70.0 320 0 {}
C {lab_pin.sym} 280 -100 0 0 {name=l22 lab=stop_lo}
C {lab_pin.sym} 320 -130 0 0 {name=l23 lab=vdd}
C {lab_pin.sym} 320 -100 0 0 {name=l24 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 300 100 0 0 {name=stoprn W=0.5 L=0.15 nf=1 mult=1 m=1}
N 320.0 70.0 320 0 {}
C {lab_pin.sym} 280 100 0 0 {name=l25 lab=stop_lo}
C {lab_pin.sym} 320 130 0 0 {name=l26 lab=vss}
C {lab_pin.sym} 320 100 0 0 {name=l27 lab=vss}
T {the input switches' NMOS line: it cannot fall until the top line is off, nor rise until the conversion line is} -260 260 0 0 0.25 0.25 {}
N 20 560 120 560 {}
C {lab_pin.sym} 20 560 0 0 {name=l28 lab=held_n}
C {sky130_fd_pr/pfet_01v8.sym} 0 360 0 0 {name=nor_heldp0 W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 20 390 0 0 {name=l29 lab=nor_held_m0}
C {lab_pin.sym} -20 360 0 0 {name=l30 lab=sample}
C {lab_pin.sym} 20 330 0 0 {name=l31 lab=vdd}
C {lab_pin.sym} 20 360 0 0 {name=l32 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 0 460 0 0 {name=nor_heldp1 W=2 L=0.15 nf=1 mult=1 m=1}
N 20.0 490.0 20 560 {}
C {lab_pin.sym} -20 460 0 0 {name=l33 lab=top_on}
C {lab_pin.sym} 20 430 0 0 {name=l34 lab=nor_held_m0}
C {lab_pin.sym} 20 460 0 0 {name=l35 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 660 0 0 {name=nor_heldn0 W=0.5 L=0.15 nf=1 mult=1 m=1}
N 20.0 630.0 20 560 {}
C {lab_pin.sym} -20 660 0 0 {name=l36 lab=sample}
C {lab_pin.sym} 20 690 0 0 {name=l37 lab=vss}
C {lab_pin.sym} 20 660 0 0 {name=l38 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 100 660 0 0 {name=nor_heldn1 W=0.5 L=0.15 nf=1 mult=1 m=1}
N 120.0 630.0 120 560 {}
C {lab_pin.sym} 80 660 0 0 {name=l39 lab=top_on}
C {lab_pin.sym} 120 690 0 0 {name=l40 lab=vss}
C {lab_pin.sym} 120 660 0 0 {name=l41 lab=vss}
N 220 560 320 560 {}
C {lab_pin.sym} 220 560 0 0 {name=l42 lab=bot_pre}
C {sky130_fd_pr/pfet_01v8.sym} 200 360 0 0 {name=nor_botp0 W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 220 390 0 0 {name=l43 lab=nor_bot_m0}
C {lab_pin.sym} 180 360 0 0 {name=l44 lab=held_n}
C {lab_pin.sym} 220 330 0 0 {name=l45 lab=vdd}
C {lab_pin.sym} 220 360 0 0 {name=l46 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 200 460 0 0 {name=nor_botp1 W=2 L=0.15 nf=1 mult=1 m=1}
N 220.0 490.0 220 560 {}
C {lab_pin.sym} 180 460 0 0 {name=l47 lab=cnv_on}
C {lab_pin.sym} 220 430 0 0 {name=l48 lab=nor_bot_m0}
C {lab_pin.sym} 220 460 0 0 {name=l49 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 200 660 0 0 {name=nor_botn0 W=0.5 L=0.15 nf=1 mult=1 m=1}
N 220.0 630.0 220 560 {}
C {lab_pin.sym} 180 660 0 0 {name=l50 lab=held_n}
C {lab_pin.sym} 220 690 0 0 {name=l51 lab=vss}
C {lab_pin.sym} 220 660 0 0 {name=l52 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 300 660 0 0 {name=nor_botn1 W=0.5 L=0.15 nf=1 mult=1 m=1}
N 320.0 630.0 320 560 {}
C {lab_pin.sym} 280 660 0 0 {name=l53 lab=cnv_on}
C {lab_pin.sym} 320 690 0 0 {name=l54 lab=vss}
C {lab_pin.sym} 320 660 0 0 {name=l55 lab=vss}
N 420 560 420 560 {}
C {lab_pin.sym} 420 560 0 0 {name=l56 lab=bbot_s0}
C {sky130_fd_pr/pfet_01v8.sym} 400 460 0 0 {name=bbot0p W=1 L=0.15 nf=1 mult=1 m=1}
N 420.0 490.0 420 560 {}
C {lab_pin.sym} 380 460 0 0 {name=l57 lab=bot_pre}
C {lab_pin.sym} 420 430 0 0 {name=l58 lab=vdd}
C {lab_pin.sym} 420 460 0 0 {name=l59 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 400 660 0 0 {name=bbot0n W=0.5 L=0.15 nf=1 mult=1 m=1}
N 420.0 630.0 420 560 {}
C {lab_pin.sym} 380 660 0 0 {name=l60 lab=bot_pre}
C {lab_pin.sym} 420 690 0 0 {name=l61 lab=vss}
C {lab_pin.sym} 420 660 0 0 {name=l62 lab=vss}
N 520 560 520 560 {}
C {lab_pin.sym} 520 560 0 0 {name=l63 lab=bbot_s1}
C {sky130_fd_pr/pfet_01v8.sym} 500 460 0 0 {name=bbot1p W=4 L=0.15 nf=1 mult=1 m=1}
N 520.0 490.0 520 560 {}
C {lab_pin.sym} 480 460 0 0 {name=l64 lab=bbot_s0}
C {lab_pin.sym} 520 430 0 0 {name=l65 lab=vdd}
C {lab_pin.sym} 520 460 0 0 {name=l66 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 500 660 0 0 {name=bbot1n W=2 L=0.15 nf=1 mult=1 m=1}
N 520.0 630.0 520 560 {}
C {lab_pin.sym} 480 660 0 0 {name=l67 lab=bbot_s0}
C {lab_pin.sym} 520 690 0 0 {name=l68 lab=vss}
C {lab_pin.sym} 520 660 0 0 {name=l69 lab=vss}
N 620 560 620 560 {}
C {lab_pin.sym} 620 560 0 0 {name=l70 lab=bbot_s2}
C {sky130_fd_pr/pfet_01v8.sym} 600 460 0 0 {name=bbot2p W=4 L=0.15 nf=1 mult=4 m=4}
N 620.0 490.0 620 560 {}
C {lab_pin.sym} 580 460 0 0 {name=l71 lab=bbot_s1}
C {lab_pin.sym} 620 430 0 0 {name=l72 lab=vdd}
C {lab_pin.sym} 620 460 0 0 {name=l73 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 600 660 0 0 {name=bbot2n W=4 L=0.15 nf=1 mult=2 m=2}
N 620.0 630.0 620 560 {}
C {lab_pin.sym} 580 660 0 0 {name=l74 lab=bbot_s1}
C {lab_pin.sym} 620 690 0 0 {name=l75 lab=vss}
C {lab_pin.sym} 620 660 0 0 {name=l76 lab=vss}
N 720 560 720 560 {}
C {lab_pin.sym} 720 560 0 0 {name=l77 lab=phi_bot}
C {sky130_fd_pr/pfet_01v8.sym} 700 460 0 0 {name=bbot3p W=4.92308 L=0.15 nf=1 mult=13 m=13}
N 720.0 490.0 720 560 {}
C {lab_pin.sym} 680 460 0 0 {name=l78 lab=bbot_s2}
C {lab_pin.sym} 720 430 0 0 {name=l79 lab=vdd}
C {lab_pin.sym} 720 460 0 0 {name=l80 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 700 660 0 0 {name=bbot3n W=4.57143 L=0.15 nf=1 mult=7 m=7}
N 720.0 630.0 720 560 {}
C {lab_pin.sym} 680 660 0 0 {name=l81 lab=bbot_s2}
C {lab_pin.sym} 720 690 0 0 {name=l82 lab=vss}
C {lab_pin.sym} 720 660 0 0 {name=l83 lab=vss}
N 820 560 820 560 {}
C {lab_pin.sym} 820 560 0 0 {name=l84 lab=sbot_lo}
C {sky130_fd_pr/pfet_01v8.sym} 800 460 0 0 {name=sbotsp W=0.42 L=1 nf=1 mult=1 m=1}
N 820.0 490.0 820 560 {}
C {lab_pin.sym} 780 460 0 0 {name=l85 lab=phi_bot}
C {lab_pin.sym} 820 430 0 0 {name=l86 lab=vdd}
C {lab_pin.sym} 820 460 0 0 {name=l87 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 800 660 0 0 {name=sbotsn W=2 L=0.15 nf=1 mult=1 m=1}
N 820.0 630.0 820 560 {}
C {lab_pin.sym} 780 660 0 0 {name=l88 lab=phi_bot}
C {lab_pin.sym} 820 690 0 0 {name=l89 lab=vss}
C {lab_pin.sym} 820 660 0 0 {name=l90 lab=vss}
N 920 560 920 560 {}
C {lab_pin.sym} 920 560 0 0 {name=l91 lab=bot_on}
C {sky130_fd_pr/pfet_01v8.sym} 900 460 0 0 {name=sbotrp W=1 L=0.15 nf=1 mult=1 m=1}
N 920.0 490.0 920 560 {}
C {lab_pin.sym} 880 460 0 0 {name=l92 lab=sbot_lo}
C {lab_pin.sym} 920 430 0 0 {name=l93 lab=vdd}
C {lab_pin.sym} 920 460 0 0 {name=l94 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 900 660 0 0 {name=sbotrn W=0.5 L=0.15 nf=1 mult=1 m=1}
N 920.0 630.0 920 560 {}
C {lab_pin.sym} 880 660 0 0 {name=l95 lab=sbot_lo}
C {lab_pin.sym} 920 690 0 0 {name=l96 lab=vss}
C {lab_pin.sym} 920 660 0 0 {name=l97 lab=vss}
T {their PMOS line: the same edge, complemented, with a detector of its own} -260 820 0 0 0.25 0.25 {}
N 20 1120 20 1120 {}
C {lab_pin.sym} 20 1120 0 0 {name=l98 lab=bbotn_s0}
C {sky130_fd_pr/pfet_01v8.sym} 0 1020 0 0 {name=bbotn0p W=4 L=0.15 nf=1 mult=1 m=1}
N 20.0 1050.0 20 1120 {}
C {lab_pin.sym} -20 1020 0 0 {name=l99 lab=bot_pre}
C {lab_pin.sym} 20 990 0 0 {name=l100 lab=vdd}
C {lab_pin.sym} 20 1020 0 0 {name=l101 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 1220 0 0 {name=bbotn0n W=2 L=0.15 nf=1 mult=1 m=1}
N 20.0 1190.0 20 1120 {}
C {lab_pin.sym} -20 1220 0 0 {name=l102 lab=bot_pre}
C {lab_pin.sym} 20 1250 0 0 {name=l103 lab=vss}
C {lab_pin.sym} 20 1220 0 0 {name=l104 lab=vss}
N 120 1120 120 1120 {}
C {lab_pin.sym} 120 1120 0 0 {name=l105 lab=bbotn_s1}
C {sky130_fd_pr/pfet_01v8.sym} 100 1020 0 0 {name=bbotn1p W=4 L=0.15 nf=1 mult=4 m=4}
N 120.0 1050.0 120 1120 {}
C {lab_pin.sym} 80 1020 0 0 {name=l106 lab=bbotn_s0}
C {lab_pin.sym} 120 990 0 0 {name=l107 lab=vdd}
C {lab_pin.sym} 120 1020 0 0 {name=l108 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 100 1220 0 0 {name=bbotn1n W=4 L=0.15 nf=1 mult=2 m=2}
N 120.0 1190.0 120 1120 {}
C {lab_pin.sym} 80 1220 0 0 {name=l109 lab=bbotn_s0}
C {lab_pin.sym} 120 1250 0 0 {name=l110 lab=vss}
C {lab_pin.sym} 120 1220 0 0 {name=l111 lab=vss}
N 220 1120 220 1120 {}
C {lab_pin.sym} 220 1120 0 0 {name=l112 lab=phi_bot_n}
C {sky130_fd_pr/pfet_01v8.sym} 200 1020 0 0 {name=bbotn2p W=4.92308 L=0.15 nf=1 mult=13 m=13}
N 220.0 1050.0 220 1120 {}
C {lab_pin.sym} 180 1020 0 0 {name=l113 lab=bbotn_s1}
C {lab_pin.sym} 220 990 0 0 {name=l114 lab=vdd}
C {lab_pin.sym} 220 1020 0 0 {name=l115 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 200 1220 0 0 {name=bbotn2n W=4.57143 L=0.15 nf=1 mult=7 m=7}
N 220.0 1190.0 220 1120 {}
C {lab_pin.sym} 180 1220 0 0 {name=l116 lab=bbotn_s1}
C {lab_pin.sym} 220 1250 0 0 {name=l117 lab=vss}
C {lab_pin.sym} 220 1220 0 0 {name=l118 lab=vss}
N 320 1120 320 1120 {}
C {lab_pin.sym} 320 1120 0 0 {name=l119 lab=sbotn_hi}
C {sky130_fd_pr/pfet_01v8.sym} 300 1020 0 0 {name=sbotnsp W=4 L=0.15 nf=1 mult=1 m=1}
N 320.0 1050.0 320 1120 {}
C {lab_pin.sym} 280 1020 0 0 {name=l120 lab=phi_bot_n}
C {lab_pin.sym} 320 990 0 0 {name=l121 lab=vdd}
C {lab_pin.sym} 320 1020 0 0 {name=l122 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 300 1220 0 0 {name=sbotnsn W=0.42 L=1 nf=1 mult=1 m=1}
N 320.0 1190.0 320 1120 {}
C {lab_pin.sym} 280 1220 0 0 {name=l123 lab=phi_bot_n}
C {lab_pin.sym} 320 1250 0 0 {name=l124 lab=vss}
C {lab_pin.sym} 320 1220 0 0 {name=l125 lab=vss}
N 420 1120 420 1120 {}
C {lab_pin.sym} 420 1120 0 0 {name=l126 lab=sbotnr_s0}
C {sky130_fd_pr/pfet_01v8.sym} 400 1020 0 0 {name=sbotnr0p W=1 L=0.15 nf=1 mult=1 m=1}
N 420.0 1050.0 420 1120 {}
C {lab_pin.sym} 380 1020 0 0 {name=l127 lab=sbotn_hi}
C {lab_pin.sym} 420 990 0 0 {name=l128 lab=vdd}
C {lab_pin.sym} 420 1020 0 0 {name=l129 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 400 1220 0 0 {name=sbotnr0n W=0.5 L=0.15 nf=1 mult=1 m=1}
N 420.0 1190.0 420 1120 {}
C {lab_pin.sym} 380 1220 0 0 {name=l130 lab=sbotn_hi}
C {lab_pin.sym} 420 1250 0 0 {name=l131 lab=vss}
C {lab_pin.sym} 420 1220 0 0 {name=l132 lab=vss}
N 520 1120 520 1120 {}
C {lab_pin.sym} 520 1120 0 0 {name=l133 lab=botn_on}
C {sky130_fd_pr/pfet_01v8.sym} 500 1020 0 0 {name=sbotnr1p W=4 L=0.15 nf=1 mult=1 m=1}
N 520.0 1050.0 520 1120 {}
C {lab_pin.sym} 480 1020 0 0 {name=l134 lab=sbotnr_s0}
C {lab_pin.sym} 520 990 0 0 {name=l135 lab=vdd}
C {lab_pin.sym} 520 1020 0 0 {name=l136 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 500 1220 0 0 {name=sbotnr1n W=2 L=0.15 nf=1 mult=1 m=1}
N 520.0 1190.0 520 1120 {}
C {lab_pin.sym} 480 1220 0 0 {name=l137 lab=sbotnr_s0}
C {lab_pin.sym} 520 1250 0 0 {name=l138 lab=vss}
C {lab_pin.sym} 520 1220 0 0 {name=l139 lab=vss}
T {the conversion switches' line: it cannot rise until both input lines are off} -260 1380 0 0 0.25 0.25 {}
N 20 1680 220 1680 {}
C {lab_pin.sym} 20 1680 0 0 {name=l140 lab=cnv_pre}
C {sky130_fd_pr/pfet_01v8.sym} 0 1380 0 0 {name=nor_cnvp0 W=3 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 20 1410 0 0 {name=l141 lab=nor_cnv_m0}
C {lab_pin.sym} -20 1380 0 0 {name=l142 lab=sample}
C {lab_pin.sym} 20 1350 0 0 {name=l143 lab=vdd}
C {lab_pin.sym} 20 1380 0 0 {name=l144 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 0 1480 0 0 {name=nor_cnvp1 W=3 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 20 1510 0 0 {name=l145 lab=nor_cnv_m1}
C {lab_pin.sym} -20 1480 0 0 {name=l146 lab=bot_on}
C {lab_pin.sym} 20 1450 0 0 {name=l147 lab=nor_cnv_m0}
C {lab_pin.sym} 20 1480 0 0 {name=l148 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 0 1580 0 0 {name=nor_cnvp2 W=3 L=0.15 nf=1 mult=1 m=1}
N 20.0 1610.0 20 1680 {}
C {lab_pin.sym} -20 1580 0 0 {name=l149 lab=botn_on}
C {lab_pin.sym} 20 1550 0 0 {name=l150 lab=nor_cnv_m1}
C {lab_pin.sym} 20 1580 0 0 {name=l151 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 1780 0 0 {name=nor_cnvn0 W=0.5 L=0.15 nf=1 mult=1 m=1}
N 20.0 1750.0 20 1680 {}
C {lab_pin.sym} -20 1780 0 0 {name=l152 lab=sample}
C {lab_pin.sym} 20 1810 0 0 {name=l153 lab=vss}
C {lab_pin.sym} 20 1780 0 0 {name=l154 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 100 1780 0 0 {name=nor_cnvn1 W=0.5 L=0.15 nf=1 mult=1 m=1}
N 120.0 1750.0 120 1680 {}
C {lab_pin.sym} 80 1780 0 0 {name=l155 lab=bot_on}
C {lab_pin.sym} 120 1810 0 0 {name=l156 lab=vss}
C {lab_pin.sym} 120 1780 0 0 {name=l157 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 1780 0 0 {name=nor_cnvn2 W=0.5 L=0.15 nf=1 mult=1 m=1}
N 220.0 1750.0 220 1680 {}
C {lab_pin.sym} 180 1780 0 0 {name=l158 lab=botn_on}
C {lab_pin.sym} 220 1810 0 0 {name=l159 lab=vss}
C {lab_pin.sym} 220 1780 0 0 {name=l160 lab=vss}
N 320 1680 320 1680 {}
C {lab_pin.sym} 320 1680 0 0 {name=l161 lab=bcnv_s0}
C {sky130_fd_pr/pfet_01v8.sym} 300 1580 0 0 {name=bcnv0p W=1 L=0.15 nf=1 mult=1 m=1}
N 320.0 1610.0 320 1680 {}
C {lab_pin.sym} 280 1580 0 0 {name=l162 lab=cnv_pre}
C {lab_pin.sym} 320 1550 0 0 {name=l163 lab=vdd}
C {lab_pin.sym} 320 1580 0 0 {name=l164 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 300 1780 0 0 {name=bcnv0n W=0.5 L=0.15 nf=1 mult=1 m=1}
N 320.0 1750.0 320 1680 {}
C {lab_pin.sym} 280 1780 0 0 {name=l165 lab=cnv_pre}
C {lab_pin.sym} 320 1810 0 0 {name=l166 lab=vss}
C {lab_pin.sym} 320 1780 0 0 {name=l167 lab=vss}
N 420 1680 420 1680 {}
C {lab_pin.sym} 420 1680 0 0 {name=l168 lab=phi_conv}
C {sky130_fd_pr/pfet_01v8.sym} 400 1580 0 0 {name=bcnv1p W=4 L=0.15 nf=1 mult=1 m=1}
N 420.0 1610.0 420 1680 {}
C {lab_pin.sym} 380 1580 0 0 {name=l169 lab=bcnv_s0}
C {lab_pin.sym} 420 1550 0 0 {name=l170 lab=vdd}
C {lab_pin.sym} 420 1580 0 0 {name=l171 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 400 1780 0 0 {name=bcnv1n W=2 L=0.15 nf=1 mult=1 m=1}
N 420.0 1750.0 420 1680 {}
C {lab_pin.sym} 380 1780 0 0 {name=l172 lab=bcnv_s0}
C {lab_pin.sym} 420 1810 0 0 {name=l173 lab=vss}
C {lab_pin.sym} 420 1780 0 0 {name=l174 lab=vss}
N 520 1680 520 1680 {}
C {lab_pin.sym} 520 1680 0 0 {name=l175 lab=scnv_lo}
C {sky130_fd_pr/pfet_01v8.sym} 500 1580 0 0 {name=scnvsp W=0.42 L=1 nf=1 mult=1 m=1}
N 520.0 1610.0 520 1680 {}
C {lab_pin.sym} 480 1580 0 0 {name=l176 lab=phi_conv}
C {lab_pin.sym} 520 1550 0 0 {name=l177 lab=vdd}
C {lab_pin.sym} 520 1580 0 0 {name=l178 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 500 1780 0 0 {name=scnvsn W=2 L=0.15 nf=1 mult=1 m=1}
N 520.0 1750.0 520 1680 {}
C {lab_pin.sym} 480 1780 0 0 {name=l179 lab=phi_conv}
C {lab_pin.sym} 520 1810 0 0 {name=l180 lab=vss}
C {lab_pin.sym} 520 1780 0 0 {name=l181 lab=vss}
N 620 1680 620 1680 {}
C {lab_pin.sym} 620 1680 0 0 {name=l182 lab=cnv_on}
C {sky130_fd_pr/pfet_01v8.sym} 600 1580 0 0 {name=scnvrp W=1 L=0.15 nf=1 mult=1 m=1}
N 620.0 1610.0 620 1680 {}
C {lab_pin.sym} 580 1580 0 0 {name=l183 lab=scnv_lo}
C {lab_pin.sym} 620 1550 0 0 {name=l184 lab=vdd}
C {lab_pin.sym} 620 1580 0 0 {name=l185 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 600 1780 0 0 {name=scnvrn W=0.5 L=0.15 nf=1 mult=1 m=1}
N 620.0 1750.0 620 1680 {}
C {lab_pin.sym} 580 1780 0 0 {name=l186 lab=scnv_lo}
C {lab_pin.sym} 620 1810 0 0 {name=l187 lab=vss}
C {lab_pin.sym} 620 1780 0 0 {name=l188 lab=vss}
C {iopin.sym} -260 -200 0 0 {name=p0 lab=vdd}
C {iopin.sym} -260 -100 0 0 {name=p1 lab=vss}
C {ipin.sym} -260 0 0 0 {name=p2 lab=sample}
C {opin.sym} -260 100 0 0 {name=p3 lab=phi_top}
C {opin.sym} -260 760 0 0 {name=p4 lab=phi_bot}
C {opin.sym} -260 1320 0 0 {name=p5 lab=phi_bot_n}
C {opin.sym} -260 1880 0 0 {name=p6 lab=phi_conv}
