v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N -1060 -520 960 -520 {lab=vdd}
N -1060 200 960 200 {lab=vss}
N 0 -520 0 -470 {lab=vdd}
N -440 -520 -440 -470 {lab=vdd}
N -860 -520 -860 -470 {lab=vdd}
N -660 -520 -660 -470 {lab=vdd}
N -180 110 -180 200 {lab=vss}
N 180 110 180 200 {lab=vss}
N -380 -120 -380 200 {lab=vss}
N 380 -120 380 200 {lab=vss}
N -540 60 -540 200 {lab=vss}
N 540 60 540 200 {lab=vss}
N -680 -120 -680 200 {lab=vss}
N 680 -120 680 200 {lab=vss}
N -820 60 -820 200 {lab=vss}
N 820 60 820 200 {lab=vss}
N -440 -250 -440 200 {lab=vss}
N -860 -230 -860 200 {lab=vss}
N -1060 -320 -1060 200 {lab=vss}
N 0 -410 0 -360 {lab=tail}
N -180 -360 180 -360 {lab=tail}
N -180 -360 -180 -310 {lab=tail}
N 180 -360 180 -310 {lab=tail}
N -180 -250 -180 -130 {lab=xn}
N -380 -180 -180 -180 {lab=xn}
N -680 -180 -380 -180 {lab=xn}
N 180 -250 180 -130 {lab=xp}
N 180 -180 380 -180 {lab=xp}
N 380 -180 680 -180 {lab=xp}
N -180 -70 -180 50 {lab=outn}
N -540 0 -180 0 {lab=outn}
N -820 0 -540 0 {lab=outn}
N 180 -70 180 50 {lab=outp}
N 180 0 540 0 {lab=outp}
N 540 0 820 0 {lab=outp}
N -180 20 -60 20 {lab=outn}
N -60 20 -60 150 {lab=outn}
N -60 150 220 150 {lab=outn}
N 220 80 220 150 {lab=outn}
N 220 -100 220 80 {lab=outn}
N 60 -20 180 -20 {lab=outp}
N 60 -20 60 170 {lab=outp}
N -220 170 60 170 {lab=outp}
N -220 80 -220 170 {lab=outp}
N -220 -100 -220 80 {lab=outp}
N -480 -440 -480 -280 {lab=clk}
N -440 -410 -440 -310 {lab=clk_i}
N -860 -410 -860 -290 {lab=bias}
N -900 -440 -900 -380 {lab=bias}
N -900 -380 -860 -380 {lab=bias}
N -1060 -380 -900 -380 {lab=bias}
N -860 -340 -790 -340 {lab=bias}
N -660 -410 -660 -340 {lab=tgate}
N -730 -340 -660 -340 {lab=tgate}
N -660 -390 -40 -390 {lab=tgate}
N -40 -440 -40 -390 {lab=tgate}
N -1000 -260 -900 -260 {lab=vref}
N -560 -360 -480 -360 {lab=clk}
N -320 -280 -220 -280 {lab=inp}
N 220 -280 320 -280 {lab=inn}
N -280 30 -180 30 {lab=outn}
N 180 30 280 30 {lab=outp}
N -790 -360 -760 -360 {lab=vss}
N -760 -360 -760 -340 {lab=vss}
C {iopin.sym} -1060 -520 2 0 {name=p0 lab=vdd}
C {iopin.sym} -1060 200 0 0 {name=p1 lab=vss}
C {ipin.sym} -1000 -260 0 0 {name=p2 lab=vref}
C {ipin.sym} -560 -360 0 0 {name=p3 lab=clk}
C {ipin.sym} -320 -280 0 0 {name=p4 lab=inp}
C {ipin.sym} 320 -280 2 0 {name=p5 lab=inn}
C {opin.sym} 280 30 0 0 {name=p6 lab=outp}
C {opin.sym} -280 30 2 0 {name=p7 lab=outn}
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
C {lab_pin.sym} -860 -440 2 0 {name=l0 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} -680 -440 0 0 {name=bgoff W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -700 -440 0 0 {name=l1 lab=clk}
C {lab_pin.sym} -660 -440 2 0 {name=l2 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} -760 -320 3 0 {name=bgon W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -760 -300 0 0 {name=l3 lab=clk}
C {lab_pin.sym} -790 -360 0 0 {name=l4 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} -880 -260 0 0 {name=bref W=1 L=2 nf=1 mult=1 m=1}
C {lab_pin.sym} -860 -260 2 0 {name=l5 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} 200 -280 0 1 {name=inn W=4 L=0.5 nf=1 mult=1 m=1}
C {lab_pin.sym} 180 -280 0 0 {name=l6 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} -200 -280 0 0 {name=inp W=4 L=0.5 nf=1 mult=1 m=1}
C {lab_pin.sym} -180 -280 2 0 {name=l7 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} -460 -280 0 0 {name=invn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -440 -310 0 0 {name=l8 lab=clk_i}
C {lab_pin.sym} -480 -280 0 0 {name=l9 lab=clk}
C {lab_pin.sym} -440 -280 2 0 {name=l10 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} -460 -440 0 0 {name=invp W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -440 -410 0 0 {name=l11 lab=clk_i}
C {lab_pin.sym} -480 -440 0 0 {name=l12 lab=clk}
C {lab_pin.sym} -440 -440 2 0 {name=l13 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} -200 -100 0 0 {name=lchn W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -180 -100 2 0 {name=l14 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 200 -100 0 1 {name=lchp W=1 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 180 -100 0 0 {name=l15 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} -200 80 0 0 {name=ldn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -180 80 0 0 {name=l16 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 200 80 0 1 {name=ldp W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 180 80 0 0 {name=l17 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} -560 30 0 0 {name=pren W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -580 30 0 0 {name=l18 lab=clk_i}
C {lab_pin.sym} -540 30 2 0 {name=l19 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 560 30 0 1 {name=prep W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 580 30 2 0 {name=l20 lab=clk_i}
C {lab_pin.sym} 540 30 0 0 {name=l21 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} -400 -150 0 0 {name=prxn W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} -420 -150 0 0 {name=l22 lab=clk_i}
C {lab_pin.sym} -380 -150 2 0 {name=l23 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 400 -150 0 1 {name=prxp W=2 L=0.15 nf=1 mult=1 m=1}
C {lab_pin.sym} 420 -150 2 0 {name=l24 lab=clk_i}
C {lab_pin.sym} 380 -150 0 0 {name=l25 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} -20 -440 0 0 {name=tail W=2 L=0.5 nf=1 mult=1 m=1}
C {lab_pin.sym} 0 -440 2 0 {name=l26 lab=vdd}
