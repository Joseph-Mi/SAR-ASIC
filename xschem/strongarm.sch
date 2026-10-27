v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
C {iopin.sym} -1060 -520 0 0 {name=p0 lab=vdd}
C {iopin.sym} -1060 200 0 0 {name=p1 lab=vss}
C {ipin.sym} -1000 -260 0 0 {name=p2 lab=vref}
C {ipin.sym} -560 -360 0 0 {name=p3 lab=clk}
C {ipin.sym} -320 -280 0 0 {name=p4 lab=inp}
C {ipin.sym} 320 -280 0 0 {name=p5 lab=inn}
C {opin.sym} 280 30 0 0 {name=p6 lab=outp}
C {opin.sym} -280 30 0 0 {name=p7 lab=outn}
N -1060 -520 960 -520 {}
N -1060 200 960 200 {}
N 0 -470 0 -520 {}
N -440 -470 -440 -520 {}
N -860 -470 -860 -520 {}
N -660 -470 -660 -520 {}
N -180 110 -180 200 {}
N 180 110 180 200 {}
N -380 -120 -380 200 {}
N 380 -120 380 200 {}
N -540 60 -540 200 {}
N 540 60 540 200 {}
N -680 -120 -680 200 {}
N 680 -120 680 200 {}
N -820 60 -820 200 {}
N 820 60 820 200 {}
N -440 -250 -440 200 {}
N -860 -230 -860 200 {}
N -1060 -320 -1060 200 {}
N 0 -410 0 -360 {}
N -180 -360 180 -360 {}
N -180 -310 -180 -360 {}
N 180 -310 180 -360 {}
N -180 -250 -180 -130 {}
N -180 -180 -380 -180 {}
N -380 -180 -680 -180 {}
N 180 -250 180 -130 {}
N 180 -180 380 -180 {}
N 380 -180 680 -180 {}
N -180 -70 -180 50 {}
N -180 0 -540 0 {}
N -540 0 -820 0 {}
N 180 -70 180 50 {}
N 180 0 540 0 {}
N 540 0 820 0 {}
N -180 20 -60 20 {}
N -60 20 -60 150 {}
N -60 150 220 150 {}
N 220 150 220 80 {}
N 220 80 220 -100 {}
N 180 -20 60 -20 {}
N 60 -20 60 170 {}
N 60 170 -220 170 {}
N -220 170 -220 80 {}
N -220 80 -220 -100 {}
N -480 -440 -480 -280 {}
N -440 -410 -440 -310 {}
N -860 -410 -860 -290 {}
N -900 -440 -900 -380 {}
N -900 -380 -860 -380 {}
N -1060 -380 -900 -380 {}
N -790 -340 -860 -340 {}
N -660 -410 -660 -340 {}
N -730 -340 -660 -340 {}
N -660 -390 -40 -390 {}
N -40 -390 -40 -440 {}
N -900 -260 -1000 -260 {}
N -480 -360 -560 -360 {}
N -220 -280 -320 -280 {}
N 220 -280 320 -280 {}
N -180 30 -280 30 {}
N 180 30 280 30 {}
C {lab_pin.sym} -900 -380 0 0 {name=nbias lab=bias}
C {lab_pin.sym} -660 -340 0 0 {name=ntgate lab=tgate}
C {lab_pin.sym} 0 -360 0 0 {name=ntail lab=tail}
C {lab_pin.sym} -180 -180 0 0 {name=nxn lab=xn}
C {lab_pin.sym} 180 -180 0 0 {name=nxp lab=xp}
C {capa.sym} -1060 -350 0 0 {name=Cbias value=1e-13}
C {capa.sym} -820 30 0 0 {name=Coutn value=1e-14}
C {capa.sym} 820 30 0 0 {name=Coutp value=1e-14}
C {capa.sym} -680 -150 0 0 {name=Cxn value=2e-13}
C {capa.sym} 680 -150 0 0 {name=Cxp value=2e-13}
C {sky130_fd_pr/pfet_01v8.sym} -880 -440 0 0 {name=bdio W=1 L=0.5 nf=1 mult=1 m=1}
C {lab_pin.sym} -860 -440 0 0 {name=l0 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} -680 -440 0 0 {name=bgoff W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -700 -440 0 0 {name=l1 lab=clk}
C {lab_pin.sym} -660 -440 0 0 {name=l2 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} -760 -320 3 0 {name=bgon W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -760 -300 0 0 {name=l3 lab=clk}
C {lab_pin.sym} -760 -340 0 0 {name=l4 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} -880 -260 0 0 {name=bref W=1 L=2 nf=1 mult=1 m=1}
C {lab_pin.sym} -860 -260 0 0 {name=l5 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} 200 -280 0 1 {name=inn W=4 L=0.5 nf=1 mult=1 m=1}
C {lab_pin.sym} 180 -280 0 0 {name=l6 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} -200 -280 0 0 {name=inp W=4 L=0.5 nf=1 mult=1 m=1}
C {lab_pin.sym} -180 -280 0 0 {name=l7 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} -460 -280 0 0 {name=invn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -440 -310 0 0 {name=l8 lab=clk_i}
C {lab_pin.sym} -480 -280 0 0 {name=l9 lab=clk}
C {lab_pin.sym} -440 -280 0 0 {name=l10 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} -460 -440 0 0 {name=invp W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -440 -410 0 0 {name=l11 lab=clk_i}
C {lab_pin.sym} -480 -440 0 0 {name=l12 lab=clk}
C {lab_pin.sym} -440 -440 0 0 {name=l13 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} -200 -100 0 0 {name=lchn W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -180 -100 0 0 {name=l14 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 200 -100 0 1 {name=lchp W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 180 -100 0 0 {name=l15 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} -200 80 0 0 {name=ldn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -180 80 0 0 {name=l16 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 80 0 1 {name=ldp W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 180 80 0 0 {name=l17 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} -560 30 0 0 {name=pren W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -580 30 0 0 {name=l18 lab=clk_i}
C {lab_pin.sym} -540 30 0 0 {name=l19 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 560 30 0 1 {name=prep W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 580 30 0 0 {name=l20 lab=clk_i}
C {lab_pin.sym} 540 30 0 0 {name=l21 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} -400 -150 0 0 {name=prxn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -420 -150 0 0 {name=l22 lab=clk_i}
C {lab_pin.sym} -380 -150 0 0 {name=l23 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 400 -150 0 1 {name=prxp W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 420 -150 0 0 {name=l24 lab=clk_i}
C {lab_pin.sym} 380 -150 0 0 {name=l25 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} -20 -440 0 0 {name=tail W=2 L=0.5 nf=1 mult=1 m=1}
C {lab_pin.sym} 0 -440 0 0 {name=l26 lab=vdd}
