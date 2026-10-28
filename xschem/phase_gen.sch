v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {phase_gen -- three switch phases from one wire, each able to change
only once the phase it must follow has finished changing (DD-11).} -260 -350 0 0 0.4 0.4 {}
T {A logic sheet: every gate is a stack, and the lines between gates are carried by
name. What matters here is which line each gate watches, which the names say.
The arrangement is sim/phase_gen.py; the circuit is sim/analog.py, netlisted back
and compared element by element by sim/tests/test_phase_gen.py.} -260 -290 0 0 0.25 0.25 {}
T {the top switch's line: it follows sample} -260 -410 0 0 0.25 0.25 {}
T {the input switches' NMOS line: it cannot fall until the top line is off, nor rise until the conversion line is} -260 260 0 0 0.25 0.25 {}
T {their PMOS line: the same edge, complemented, with a detector of its own} -260 820 0 0 0.25 0.25 {}
T {the conversion switches' line: it cannot rise until both input lines are off} -260 1380 0 0 0.25 0.25 {}
N 20 -70 20 0 {lab=btop_s0}
N 20 0 20 70 {lab=btop_s0}
N 190 -70 190 0 {lab=phi_top}
N 190 0 190 70 {lab=phi_top}
N 360 -70 360 0 {lab=stop_lo}
N 360 0 360 70 {lab=stop_lo}
N 530 -70 530 0 {lab=top_on}
N 530 0 530 70 {lab=top_on}
N 20 560 120 560 {lab=held_n}
N 20 490 20 560 {lab=held_n}
N 20 560 20 630 {lab=held_n}
N 200 560 200 630 {lab=held_n}
N 390 560 490 560 {lab=bot_pre}
N 390 490 390 560 {lab=bot_pre}
N 390 560 390 630 {lab=bot_pre}
N 580 560 580 630 {lab=bot_pre}
N 830 490 830 560 {lab=bbot_s0}
N 830 560 830 630 {lab=bbot_s0}
N 1010 490 1010 560 {lab=bbot_s1}
N 1010 560 1010 630 {lab=bbot_s1}
N 1190 490 1190 560 {lab=bbot_s2}
N 1190 560 1190 630 {lab=bbot_s2}
N 1360 490 1360 560 {lab=phi_bot}
N 1360 560 1360 630 {lab=phi_bot}
N 1530 490 1530 560 {lab=sbot_lo}
N 1530 560 1530 630 {lab=sbot_lo}
N 1700 490 1700 560 {lab=bot_on}
N 1700 560 1700 630 {lab=bot_on}
N 20 1050 20 1120 {lab=bbotn_s0}
N 20 1120 20 1190 {lab=bbotn_s0}
N 210 1050 210 1120 {lab=bbotn_s1}
N 210 1120 210 1190 {lab=bbotn_s1}
N 400 1050 400 1120 {lab=phi_bot_n}
N 400 1120 400 1190 {lab=phi_bot_n}
N 580 1050 580 1120 {lab=sbotn_hi}
N 580 1120 580 1190 {lab=sbotn_hi}
N 770 1050 770 1120 {lab=sbotnr_s0}
N 770 1120 770 1190 {lab=sbotnr_s0}
N 950 1050 950 1120 {lab=botn_on}
N 950 1120 950 1190 {lab=botn_on}
N 20 1680 220 1680 {lab=cnv_pre}
N 20 1610 20 1680 {lab=cnv_pre}
N 20 1680 20 1750 {lab=cnv_pre}
N 200 1680 200 1750 {lab=cnv_pre}
N 380 1680 380 1750 {lab=cnv_pre}
N 560 1610 560 1680 {lab=bcnv_s0}
N 560 1680 560 1750 {lab=bcnv_s0}
N 750 1610 750 1680 {lab=phi_conv}
N 750 1680 750 1750 {lab=phi_conv}
N 920 1610 920 1680 {lab=scnv_lo}
N 920 1680 920 1750 {lab=scnv_lo}
N 1090 1610 1090 1680 {lab=cnv_on}
N 1090 1680 1090 1750 {lab=cnv_on}
N 300 1680 340 1680 {lab=cnv_pre}
N 340 1680 380 1680 {lab=cnv_pre}
N 220 1680 300 1680 {lab=cnv_pre}
N 490 560 580 560 {lab=bot_pre}
N 130 560 200 560 {lab=held_n}
N 120 560 130 560 {lab=held_n}
C {lab_pin.sym} 20 0 0 0 {name=l0 lab=btop_s0}
C {sky130_fd_pr/pfet_01v8.sym} 0 -100 0 0 {name=btop0p W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 -100 0 0 {name=l1 lab=sample}
C {lab_pin.sym} 20 -130 0 0 {name=l2 lab=vdd}
C {lab_pin.sym} 20 -100 2 0 {name=l3 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 100 0 0 {name=btop0n W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 100 0 0 {name=l4 lab=sample}
C {lab_pin.sym} 20 130 0 0 {name=l5 lab=vss}
C {lab_pin.sym} 20 100 2 0 {name=l6 lab=vss}
C {lab_pin.sym} 190 0 0 0 {name=l7 lab=phi_top}
C {sky130_fd_pr/pfet_01v8.sym} 170 -100 0 0 {name=btop1p W=4 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 150 -100 0 0 {name=l8 lab=btop_s0}
C {lab_pin.sym} 190 -130 0 0 {name=l9 lab=vdd}
C {lab_pin.sym} 190 -100 2 0 {name=l10 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 170 100 0 0 {name=btop1n W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 150 100 0 0 {name=l11 lab=btop_s0}
C {lab_pin.sym} 190 130 0 0 {name=l12 lab=vss}
C {lab_pin.sym} 190 100 2 0 {name=l13 lab=vss}
C {lab_pin.sym} 360 0 0 0 {name=l14 lab=stop_lo}
C {sky130_fd_pr/pfet_01v8.sym} 340 -100 0 0 {name=stopsp W=0.42 L=1 nf=1 mult=1 m=1}
C {lab_pin.sym} 320 -100 0 0 {name=l15 lab=phi_top}
C {lab_pin.sym} 360 -130 0 0 {name=l16 lab=vdd}
C {lab_pin.sym} 360 -100 2 0 {name=l17 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 340 100 0 0 {name=stopsn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 320 100 0 0 {name=l18 lab=phi_top}
C {lab_pin.sym} 360 130 0 0 {name=l19 lab=vss}
C {lab_pin.sym} 360 100 2 0 {name=l20 lab=vss}
C {lab_pin.sym} 530 0 0 0 {name=l21 lab=top_on}
C {sky130_fd_pr/pfet_01v8.sym} 510 -100 0 0 {name=stoprp W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 490 -100 0 0 {name=l22 lab=stop_lo}
C {lab_pin.sym} 530 -130 0 0 {name=l23 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 510 100 0 0 {name=stoprn W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 490 100 0 0 {name=l25 lab=stop_lo}
C {lab_pin.sym} 530 130 0 0 {name=l26 lab=vss}
C {lab_pin.sym} 530 100 2 0 {name=l27 lab=vss}
C {lab_pin.sym} 20 560 0 0 {name=l28 lab=held_n}
C {sky130_fd_pr/pfet_01v8.sym} 0 360 0 0 {name=nor_heldp0 W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 20 390 0 0 {name=l29 lab=nor_held_m0}
C {lab_pin.sym} -20 360 0 0 {name=l30 lab=sample}
C {lab_pin.sym} 20 330 0 0 {name=l31 lab=vdd}
C {lab_pin.sym} 20 360 2 0 {name=l32 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 0 460 0 0 {name=nor_heldp1 W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 460 0 0 {name=l33 lab=top_on}
C {lab_pin.sym} 20 430 0 0 {name=l34 lab=nor_held_m0}
C {lab_pin.sym} 20 460 2 0 {name=l35 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 660 0 0 {name=nor_heldn0 W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 660 0 0 {name=l36 lab=sample}
C {lab_pin.sym} 20 690 0 0 {name=l37 lab=vss}
C {lab_pin.sym} 20 660 0 0 {name=l38 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 180 660 0 0 {name=nor_heldn1 W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 160 660 0 0 {name=l39 lab=top_on}
C {lab_pin.sym} 200 690 0 0 {name=l40 lab=vss}
C {lab_pin.sym} 200 660 2 0 {name=l41 lab=vss}
C {lab_pin.sym} 390 560 0 0 {name=l42 lab=bot_pre}
C {sky130_fd_pr/pfet_01v8.sym} 370 360 0 0 {name=nor_botp0 W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 390 390 0 0 {name=l43 lab=nor_bot_m0}
C {lab_pin.sym} 350 360 0 0 {name=l44 lab=held_n}
C {lab_pin.sym} 390 330 0 0 {name=l45 lab=vdd}
C {lab_pin.sym} 390 360 2 0 {name=l46 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 370 460 0 0 {name=nor_botp1 W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 350 460 0 0 {name=l47 lab=cnv_on}
C {lab_pin.sym} 390 430 0 0 {name=l48 lab=nor_bot_m0}
C {lab_pin.sym} 390 460 2 0 {name=l49 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 370 660 0 0 {name=nor_botn0 W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 350 660 0 0 {name=l50 lab=held_n}
C {lab_pin.sym} 390 690 0 0 {name=l51 lab=vss}
C {lab_pin.sym} 390 660 2 0 {name=l52 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 560 660 0 0 {name=nor_botn1 W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 540 660 0 0 {name=l53 lab=cnv_on}
C {lab_pin.sym} 580 690 0 0 {name=l54 lab=vss}
C {lab_pin.sym} 580 660 2 0 {name=l55 lab=vss}
C {lab_pin.sym} 830 560 0 0 {name=l56 lab=bbot_s0}
C {sky130_fd_pr/pfet_01v8.sym} 810 460 0 0 {name=bbot0p W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 790 460 0 0 {name=l57 lab=bot_pre}
C {lab_pin.sym} 830 430 0 0 {name=l58 lab=vdd}
C {lab_pin.sym} 830 460 2 0 {name=l59 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 810 660 0 0 {name=bbot0n W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 790 660 0 0 {name=l60 lab=bot_pre}
C {lab_pin.sym} 830 690 0 0 {name=l61 lab=vss}
C {lab_pin.sym} 830 660 2 0 {name=l62 lab=vss}
C {lab_pin.sym} 1010 560 0 0 {name=l63 lab=bbot_s1}
C {sky130_fd_pr/pfet_01v8.sym} 990 460 0 0 {name=bbot1p W=4 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 970 460 0 0 {name=l64 lab=bbot_s0}
C {lab_pin.sym} 1010 430 0 0 {name=l65 lab=vdd}
C {lab_pin.sym} 1010 460 2 0 {name=l66 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 990 660 0 0 {name=bbot1n W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 970 660 0 0 {name=l67 lab=bbot_s0}
C {lab_pin.sym} 1010 690 0 0 {name=l68 lab=vss}
C {lab_pin.sym} 1010 660 2 0 {name=l69 lab=vss}
C {lab_pin.sym} 1190 560 0 0 {name=l70 lab=bbot_s2}
C {sky130_fd_pr/pfet_01v8.sym} 1170 460 0 0 {name=bbot2p W=4 L=0.15 nf=1 mult=4 m=4}
C {lab_pin.sym} 1150 460 0 0 {name=l71 lab=bbot_s1}
C {lab_pin.sym} 1190 430 0 0 {name=l72 lab=vdd}
C {lab_pin.sym} 1190 460 2 0 {name=l73 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 1170 660 0 0 {name=bbot2n W=4 L=0.15 nf=1 mult=2 m=2}
C {lab_pin.sym} 1150 660 0 0 {name=l74 lab=bbot_s1}
C {lab_pin.sym} 1190 690 0 0 {name=l75 lab=vss}
C {lab_pin.sym} 1190 660 2 0 {name=l76 lab=vss}
C {lab_pin.sym} 1360 560 0 0 {name=l77 lab=phi_bot}
C {sky130_fd_pr/pfet_01v8.sym} 1340 460 0 0 {name=bbot3p W=4.92308 L=0.15 nf=1 mult=13 m=13}
C {lab_pin.sym} 1320 460 0 0 {name=l78 lab=bbot_s2}
C {lab_pin.sym} 1360 430 0 0 {name=l79 lab=vdd}
C {lab_pin.sym} 1360 460 2 0 {name=l80 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 1340 660 0 0 {name=bbot3n W=4.57143 L=0.15 nf=1 mult=7 m=7}
C {lab_pin.sym} 1320 660 0 0 {name=l81 lab=bbot_s2}
C {lab_pin.sym} 1360 690 0 0 {name=l82 lab=vss}
C {lab_pin.sym} 1360 660 2 0 {name=l83 lab=vss}
C {lab_pin.sym} 1530 560 0 0 {name=l84 lab=sbot_lo}
C {sky130_fd_pr/pfet_01v8.sym} 1510 460 0 0 {name=sbotsp W=0.42 L=1 nf=1 mult=1 m=1}
C {lab_pin.sym} 1490 460 0 0 {name=l85 lab=phi_bot}
C {lab_pin.sym} 1530 430 0 0 {name=l86 lab=vdd}
C {lab_pin.sym} 1530 460 2 0 {name=l87 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 1510 660 0 0 {name=sbotsn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 1490 660 0 0 {name=l88 lab=phi_bot}
C {lab_pin.sym} 1530 690 0 0 {name=l89 lab=vss}
C {lab_pin.sym} 1530 660 2 0 {name=l90 lab=vss}
C {lab_pin.sym} 1700 560 0 0 {name=l91 lab=bot_on}
C {sky130_fd_pr/pfet_01v8.sym} 1680 460 0 0 {name=sbotrp W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 1660 460 0 0 {name=l92 lab=sbot_lo}
C {lab_pin.sym} 1700 430 0 0 {name=l93 lab=vdd}
C {lab_pin.sym} 1700 460 2 0 {name=l94 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 1680 660 0 0 {name=sbotrn W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 1660 660 0 0 {name=l95 lab=sbot_lo}
C {lab_pin.sym} 1700 690 0 0 {name=l96 lab=vss}
C {lab_pin.sym} 1700 660 2 0 {name=l97 lab=vss}
C {lab_pin.sym} 20 1120 0 0 {name=l98 lab=bbotn_s0}
C {sky130_fd_pr/pfet_01v8.sym} 0 1020 0 0 {name=bbotn0p W=4 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 1020 0 0 {name=l99 lab=bot_pre}
C {lab_pin.sym} 20 990 0 0 {name=l100 lab=vdd}
C {lab_pin.sym} 20 1020 2 0 {name=l101 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 1220 0 0 {name=bbotn0n W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 1220 0 0 {name=l102 lab=bot_pre}
C {lab_pin.sym} 20 1250 0 0 {name=l103 lab=vss}
C {lab_pin.sym} 20 1220 0 0 {name=l104 lab=vss}
C {lab_pin.sym} 210 1120 0 0 {name=l105 lab=bbotn_s1}
C {sky130_fd_pr/pfet_01v8.sym} 190 1020 0 0 {name=bbotn1p W=4 L=0.15 nf=1 mult=4 m=4}
C {lab_pin.sym} 170 1020 0 0 {name=l106 lab=bbotn_s0}
C {lab_pin.sym} 210 990 0 0 {name=l107 lab=vdd}
C {lab_pin.sym} 210 1020 2 0 {name=l108 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 190 1220 0 0 {name=bbotn1n W=4 L=0.15 nf=1 mult=2 m=2}
C {lab_pin.sym} 170 1220 0 0 {name=l109 lab=bbotn_s0}
C {lab_pin.sym} 210 1250 0 0 {name=l110 lab=vss}
C {lab_pin.sym} 210 1220 2 0 {name=l111 lab=vss}
C {lab_pin.sym} 400 1120 0 0 {name=l112 lab=phi_bot_n}
C {sky130_fd_pr/pfet_01v8.sym} 380 1020 0 0 {name=bbotn2p W=4.92308 L=0.15 nf=1 mult=13 m=13}
C {lab_pin.sym} 360 1020 0 0 {name=l113 lab=bbotn_s1}
C {lab_pin.sym} 400 990 0 0 {name=l114 lab=vdd}
C {lab_pin.sym} 400 1020 2 0 {name=l115 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 380 1220 0 0 {name=bbotn2n W=4.57143 L=0.15 nf=1 mult=7 m=7}
C {lab_pin.sym} 360 1220 0 0 {name=l116 lab=bbotn_s1}
C {lab_pin.sym} 400 1250 0 0 {name=l117 lab=vss}
C {lab_pin.sym} 400 1220 2 0 {name=l118 lab=vss}
C {lab_pin.sym} 580 1120 0 0 {name=l119 lab=sbotn_hi}
C {sky130_fd_pr/pfet_01v8.sym} 560 1020 0 0 {name=sbotnsp W=4 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 540 1020 0 0 {name=l120 lab=phi_bot_n}
C {lab_pin.sym} 580 990 0 0 {name=l121 lab=vdd}
C {lab_pin.sym} 580 1020 2 0 {name=l122 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 560 1220 0 0 {name=sbotnsn W=0.42 L=1 nf=1 mult=1 m=1}
C {lab_pin.sym} 540 1220 0 0 {name=l123 lab=phi_bot_n}
C {lab_pin.sym} 580 1250 0 0 {name=l124 lab=vss}
C {lab_pin.sym} 580 1220 2 0 {name=l125 lab=vss}
C {lab_pin.sym} 770 1120 0 0 {name=l126 lab=sbotnr_s0}
C {sky130_fd_pr/pfet_01v8.sym} 750 1020 0 0 {name=sbotnr0p W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 730 1020 0 0 {name=l127 lab=sbotn_hi}
C {lab_pin.sym} 770 990 0 0 {name=l128 lab=vdd}
C {lab_pin.sym} 770 1020 2 0 {name=l129 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 750 1220 0 0 {name=sbotnr0n W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 730 1220 0 0 {name=l130 lab=sbotn_hi}
C {lab_pin.sym} 770 1250 0 0 {name=l131 lab=vss}
C {lab_pin.sym} 770 1220 2 0 {name=l132 lab=vss}
C {lab_pin.sym} 950 1120 0 0 {name=l133 lab=botn_on}
C {sky130_fd_pr/pfet_01v8.sym} 930 1020 0 0 {name=sbotnr1p W=4 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 910 1020 0 0 {name=l134 lab=sbotnr_s0}
C {lab_pin.sym} 950 990 0 0 {name=l135 lab=vdd}
C {lab_pin.sym} 950 1020 2 0 {name=l136 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 930 1220 0 0 {name=sbotnr1n W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 910 1220 0 0 {name=l137 lab=sbotnr_s0}
C {lab_pin.sym} 950 1250 0 0 {name=l138 lab=vss}
C {lab_pin.sym} 950 1220 2 0 {name=l139 lab=vss}
C {lab_pin.sym} 20 1680 0 0 {name=l140 lab=cnv_pre}
C {sky130_fd_pr/pfet_01v8.sym} 0 1380 0 0 {name=nor_cnvp0 W=3 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 20 1410 0 0 {name=l141 lab=nor_cnv_m0}
C {lab_pin.sym} -20 1380 0 0 {name=l142 lab=sample}
C {lab_pin.sym} 20 1350 0 0 {name=l143 lab=vdd}
C {lab_pin.sym} 20 1380 2 0 {name=l144 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 0 1480 0 0 {name=nor_cnvp1 W=3 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 20 1510 0 0 {name=l145 lab=nor_cnv_m1}
C {lab_pin.sym} -20 1480 0 0 {name=l146 lab=bot_on}
C {lab_pin.sym} 20 1450 0 0 {name=l147 lab=nor_cnv_m0}
C {lab_pin.sym} 20 1480 2 0 {name=l148 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 0 1580 0 0 {name=nor_cnvp2 W=3 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 1580 0 0 {name=l149 lab=botn_on}
C {lab_pin.sym} 20 1550 0 0 {name=l150 lab=nor_cnv_m1}
C {lab_pin.sym} 20 1580 2 0 {name=l151 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 1780 0 0 {name=nor_cnvn0 W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -20 1780 0 0 {name=l152 lab=sample}
C {lab_pin.sym} 20 1810 0 0 {name=l153 lab=vss}
C {lab_pin.sym} 20 1780 2 0 {name=l154 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 180 1780 0 0 {name=nor_cnvn1 W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 160 1780 0 0 {name=l155 lab=bot_on}
C {lab_pin.sym} 200 1810 0 0 {name=l156 lab=vss}
C {lab_pin.sym} 200 1780 2 0 {name=l157 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 360 1780 0 0 {name=nor_cnvn2 W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 340 1780 0 0 {name=l158 lab=botn_on}
C {lab_pin.sym} 380 1810 0 0 {name=l159 lab=vss}
C {lab_pin.sym} 380 1780 2 0 {name=l160 lab=vss}
C {lab_pin.sym} 560 1680 0 0 {name=l161 lab=bcnv_s0}
C {sky130_fd_pr/pfet_01v8.sym} 540 1580 0 0 {name=bcnv0p W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 520 1580 0 0 {name=l162 lab=cnv_pre}
C {lab_pin.sym} 560 1550 0 0 {name=l163 lab=vdd}
C {lab_pin.sym} 560 1580 2 0 {name=l164 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 540 1780 0 0 {name=bcnv0n W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 520 1780 0 0 {name=l165 lab=cnv_pre}
C {lab_pin.sym} 560 1810 0 0 {name=l166 lab=vss}
C {lab_pin.sym} 560 1780 2 0 {name=l167 lab=vss}
C {lab_pin.sym} 750 1680 0 0 {name=l168 lab=phi_conv}
C {sky130_fd_pr/pfet_01v8.sym} 730 1580 0 0 {name=bcnv1p W=4 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 710 1580 0 0 {name=l169 lab=bcnv_s0}
C {lab_pin.sym} 750 1550 0 0 {name=l170 lab=vdd}
C {lab_pin.sym} 750 1580 2 0 {name=l171 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 730 1780 0 0 {name=bcnv1n W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 710 1780 0 0 {name=l172 lab=bcnv_s0}
C {lab_pin.sym} 750 1810 0 0 {name=l173 lab=vss}
C {lab_pin.sym} 750 1780 2 0 {name=l174 lab=vss}
C {lab_pin.sym} 920 1680 0 0 {name=l175 lab=scnv_lo}
C {sky130_fd_pr/pfet_01v8.sym} 900 1580 0 0 {name=scnvsp W=0.42 L=1 nf=1 mult=1 m=1}
C {lab_pin.sym} 880 1580 0 0 {name=l176 lab=phi_conv}
C {lab_pin.sym} 920 1550 0 0 {name=l177 lab=vdd}
C {lab_pin.sym} 920 1580 2 0 {name=l178 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 900 1780 0 0 {name=scnvsn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 880 1780 0 0 {name=l179 lab=phi_conv}
C {lab_pin.sym} 920 1810 0 0 {name=l180 lab=vss}
C {lab_pin.sym} 920 1780 2 0 {name=l181 lab=vss}
C {lab_pin.sym} 1090 1680 0 0 {name=l182 lab=cnv_on}
C {sky130_fd_pr/pfet_01v8.sym} 1070 1580 0 0 {name=scnvrp W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 1050 1580 0 0 {name=l183 lab=scnv_lo}
C {lab_pin.sym} 1090 1550 0 0 {name=l184 lab=vdd}
C {lab_pin.sym} 1090 1580 2 0 {name=l185 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 1070 1780 0 0 {name=scnvrn W=0.5 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 1050 1780 0 0 {name=l186 lab=scnv_lo}
C {lab_pin.sym} 1090 1810 0 0 {name=l187 lab=vss}
C {lab_pin.sym} 1090 1780 2 0 {name=l188 lab=vss}
C {iopin.sym} -240 -120 0 0 {name=p0 lab=vdd}
C {iopin.sym} -240 -90 0 0 {name=p1 lab=vss}
C {ipin.sym} -240 -70 0 0 {name=p2 lab=sample}
C {opin.sym} -240 -50 0 0 {name=p3 lab=phi_top}
C {opin.sym} -240 -20 0 0 {name=p4 lab=phi_bot}
C {opin.sym} -240 10 0 0 {name=p5 lab=phi_bot_n}
C {opin.sym} -240 40 0 0 {name=p6 lab=phi_conv}
C {lab_pin.sym} 530 -100 2 0 {name=l189 lab=vdd}
