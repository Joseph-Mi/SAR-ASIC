v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
C {iopin.sym} -320 0 0 0 {name=p0 lab=vdd}
C {iopin.sym} -320 40 0 0 {name=p1 lab=vss}
C {ipin.sym} -320 80 0 0 {name=p2 lab=vref}
C {ipin.sym} -320 120 0 0 {name=p3 lab=clk}
C {ipin.sym} -320 160 0 0 {name=p4 lab=inp}
C {ipin.sym} -320 200 0 0 {name=p5 lab=inn}
C {opin.sym} -320 240 0 0 {name=p6 lab=outp}
C {opin.sym} -320 280 0 0 {name=p7 lab=outn}
C {sky130_fd_pr/pfet_01v8.sym} 0 0 0 0 {name=invp W=2 L=0.15 nf=1 mult=1 m=1}
N 20 30 20 60 {lab=clk_i}
C {lab_pin.sym} 20 60 0 0 {name=l0 lab=clk_i}
N -20 0 -80 0 {lab=clk}
C {lab_pin.sym} -80 0 0 0 {name=l1 lab=clk}
N 20 -30 20 -60 {lab=vdd}
C {lab_pin.sym} 20 -60 0 0 {name=l2 lab=vdd}
N 20 0 80 0 {lab=vdd}
C {lab_pin.sym} 80 0 0 0 {name=l3 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 240 0 0 0 {name=invn W=2 L=0.15 nf=1 mult=1 m=1}
N 260 -30 260 -60 {lab=clk_i}
C {lab_pin.sym} 260 -60 0 0 {name=l4 lab=clk_i}
N 220 0 160 0 {lab=clk}
C {lab_pin.sym} 160 0 0 0 {name=l5 lab=clk}
N 260 30 260 60 {lab=vss}
C {lab_pin.sym} 260 60 0 0 {name=l6 lab=vss}
N 260 0 320 0 {lab=vss}
C {lab_pin.sym} 320 0 0 0 {name=l7 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 480 0 0 0 {name=bref W=1 L=2 nf=1 mult=1 m=1}
N 500 -30 500 -60 {lab=bias}
C {lab_pin.sym} 500 -60 0 0 {name=l8 lab=bias}
N 460 0 400 0 {lab=vref}
C {lab_pin.sym} 400 0 0 0 {name=l9 lab=vref}
N 500 30 500 60 {lab=vss}
C {lab_pin.sym} 500 60 0 0 {name=l10 lab=vss}
N 500 0 560 0 {lab=vss}
C {lab_pin.sym} 560 0 0 0 {name=l11 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} 720 0 0 0 {name=bdio W=1 L=0.5 nf=1 mult=1 m=1}
N 740 30 740 60 {lab=bias}
C {lab_pin.sym} 740 60 0 0 {name=l12 lab=bias}
N 700 0 640 0 {lab=bias}
C {lab_pin.sym} 640 0 0 0 {name=l13 lab=bias}
N 740 -30 740 -60 {lab=vdd}
C {lab_pin.sym} 740 -60 0 0 {name=l14 lab=vdd}
N 740 0 800 0 {lab=vdd}
C {lab_pin.sym} 800 0 0 0 {name=l15 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 960 0 0 0 {name=bgoff W=1 L=0.15 nf=1 mult=1 m=1}
N 980 30 980 60 {lab=tgate}
C {lab_pin.sym} 980 60 0 0 {name=l16 lab=tgate}
N 940 0 880 0 {lab=clk}
C {lab_pin.sym} 880 0 0 0 {name=l17 lab=clk}
N 980 -30 980 -60 {lab=vdd}
C {lab_pin.sym} 980 -60 0 0 {name=l18 lab=vdd}
N 980 0 1040 0 {lab=vdd}
C {lab_pin.sym} 1040 0 0 0 {name=l19 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 0 200 0 0 {name=bgon W=1 L=0.15 nf=1 mult=1 m=1}
N 20 170 20 140 {lab=bias}
C {lab_pin.sym} 20 140 0 0 {name=l20 lab=bias}
N -20 200 -80 200 {lab=clk}
C {lab_pin.sym} -80 200 0 0 {name=l21 lab=clk}
N 20 230 20 260 {lab=tgate}
C {lab_pin.sym} 20 260 0 0 {name=l22 lab=tgate}
N 20 200 80 200 {lab=vss}
C {lab_pin.sym} 80 200 0 0 {name=l23 lab=vss}
C {capa.sym} 240 200 0 0 {name=Cbias value=1e-13}
N 240 170 240 140 {lab=bias}
C {lab_pin.sym} 240 140 0 0 {name=l24 lab=bias}
N 240 230 240 260 {lab=vss}
C {lab_pin.sym} 240 260 0 0 {name=l25 lab=vss}
C {sky130_fd_pr/pfet_01v8.sym} 480 200 0 0 {name=tail W=2 L=0.5 nf=1 mult=1 m=1}
N 500 230 500 260 {lab=tail}
C {lab_pin.sym} 500 260 0 0 {name=l26 lab=tail}
N 460 200 400 200 {lab=tgate}
C {lab_pin.sym} 400 200 0 0 {name=l27 lab=tgate}
N 500 170 500 140 {lab=vdd}
C {lab_pin.sym} 500 140 0 0 {name=l28 lab=vdd}
N 500 200 560 200 {lab=vdd}
C {lab_pin.sym} 560 200 0 0 {name=l29 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 720 200 0 0 {name=inp W=4 L=0.5 nf=1 mult=1 m=1}
N 740 230 740 260 {lab=xn}
C {lab_pin.sym} 740 260 0 0 {name=l30 lab=xn}
N 700 200 640 200 {lab=inp}
C {lab_pin.sym} 640 200 0 0 {name=l31 lab=inp}
N 740 170 740 140 {lab=tail}
C {lab_pin.sym} 740 140 0 0 {name=l32 lab=tail}
N 740 200 800 200 {lab=vdd}
C {lab_pin.sym} 800 200 0 0 {name=l33 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 960 200 0 0 {name=inn W=4 L=0.5 nf=1 mult=1 m=1}
N 980 230 980 260 {lab=xp}
C {lab_pin.sym} 980 260 0 0 {name=l34 lab=xp}
N 940 200 880 200 {lab=inn}
C {lab_pin.sym} 880 200 0 0 {name=l35 lab=inn}
N 980 170 980 140 {lab=tail}
C {lab_pin.sym} 980 140 0 0 {name=l36 lab=tail}
N 980 200 1040 200 {lab=vdd}
C {lab_pin.sym} 1040 200 0 0 {name=l37 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 0 400 0 0 {name=lchp W=1 L=0.15 nf=1 mult=1 m=1}
N 20 430 20 460 {lab=outp}
C {lab_pin.sym} 20 460 0 0 {name=l38 lab=outp}
N -20 400 -80 400 {lab=outn}
C {lab_pin.sym} -80 400 0 0 {name=l39 lab=outn}
N 20 370 20 340 {lab=xp}
C {lab_pin.sym} 20 340 0 0 {name=l40 lab=xp}
N 20 400 80 400 {lab=vdd}
C {lab_pin.sym} 80 400 0 0 {name=l41 lab=vdd}
C {sky130_fd_pr/pfet_01v8.sym} 240 400 0 0 {name=lchn W=1 L=0.15 nf=1 mult=1 m=1}
N 260 430 260 460 {lab=outn}
C {lab_pin.sym} 260 460 0 0 {name=l42 lab=outn}
N 220 400 160 400 {lab=outp}
C {lab_pin.sym} 160 400 0 0 {name=l43 lab=outp}
N 260 370 260 340 {lab=xn}
C {lab_pin.sym} 260 340 0 0 {name=l44 lab=xn}
N 260 400 320 400 {lab=vdd}
C {lab_pin.sym} 320 400 0 0 {name=l45 lab=vdd}
C {sky130_fd_pr/nfet_01v8.sym} 480 400 0 0 {name=ldp W=2 L=0.15 nf=1 mult=1 m=1}
N 500 370 500 340 {lab=outp}
C {lab_pin.sym} 500 340 0 0 {name=l46 lab=outp}
N 460 400 400 400 {lab=outn}
C {lab_pin.sym} 400 400 0 0 {name=l47 lab=outn}
N 500 430 500 460 {lab=vss}
C {lab_pin.sym} 500 460 0 0 {name=l48 lab=vss}
N 500 400 560 400 {lab=vss}
C {lab_pin.sym} 560 400 0 0 {name=l49 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 720 400 0 0 {name=ldn W=2 L=0.15 nf=1 mult=1 m=1}
N 740 370 740 340 {lab=outn}
C {lab_pin.sym} 740 340 0 0 {name=l50 lab=outn}
N 700 400 640 400 {lab=outp}
C {lab_pin.sym} 640 400 0 0 {name=l51 lab=outp}
N 740 430 740 460 {lab=vss}
C {lab_pin.sym} 740 460 0 0 {name=l52 lab=vss}
N 740 400 800 400 {lab=vss}
C {lab_pin.sym} 800 400 0 0 {name=l53 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 960 400 0 0 {name=prep W=2 L=0.15 nf=1 mult=1 m=1}
N 980 370 980 340 {lab=outp}
C {lab_pin.sym} 980 340 0 0 {name=l54 lab=outp}
N 940 400 880 400 {lab=clk_i}
C {lab_pin.sym} 880 400 0 0 {name=l55 lab=clk_i}
N 980 430 980 460 {lab=vss}
C {lab_pin.sym} 980 460 0 0 {name=l56 lab=vss}
N 980 400 1040 400 {lab=vss}
C {lab_pin.sym} 1040 400 0 0 {name=l57 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 0 600 0 0 {name=pren W=2 L=0.15 nf=1 mult=1 m=1}
N 20 570 20 540 {lab=outn}
C {lab_pin.sym} 20 540 0 0 {name=l58 lab=outn}
N -20 600 -80 600 {lab=clk_i}
C {lab_pin.sym} -80 600 0 0 {name=l59 lab=clk_i}
N 20 630 20 660 {lab=vss}
C {lab_pin.sym} 20 660 0 0 {name=l60 lab=vss}
N 20 600 80 600 {lab=vss}
C {lab_pin.sym} 80 600 0 0 {name=l61 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 240 600 0 0 {name=prxp W=2 L=0.15 nf=1 mult=1 m=1}
N 260 570 260 540 {lab=xp}
C {lab_pin.sym} 260 540 0 0 {name=l62 lab=xp}
N 220 600 160 600 {lab=clk_i}
C {lab_pin.sym} 160 600 0 0 {name=l63 lab=clk_i}
N 260 630 260 660 {lab=vss}
C {lab_pin.sym} 260 660 0 0 {name=l64 lab=vss}
N 260 600 320 600 {lab=vss}
C {lab_pin.sym} 320 600 0 0 {name=l65 lab=vss}
C {sky130_fd_pr/nfet_01v8.sym} 480 600 0 0 {name=prxn W=2 L=0.15 nf=1 mult=1 m=1}
N 500 570 500 540 {lab=xn}
C {lab_pin.sym} 500 540 0 0 {name=l66 lab=xn}
N 460 600 400 600 {lab=clk_i}
C {lab_pin.sym} 400 600 0 0 {name=l67 lab=clk_i}
N 500 630 500 660 {lab=vss}
C {lab_pin.sym} 500 660 0 0 {name=l68 lab=vss}
N 500 600 560 600 {lab=vss}
C {lab_pin.sym} 560 600 0 0 {name=l69 lab=vss}
C {capa.sym} 720 600 0 0 {name=Cxp value=2e-13}
N 720 570 720 540 {lab=xp}
C {lab_pin.sym} 720 540 0 0 {name=l70 lab=xp}
N 720 630 720 660 {lab=vss}
C {lab_pin.sym} 720 660 0 0 {name=l71 lab=vss}
C {capa.sym} 960 600 0 0 {name=Cxn value=2e-13}
N 960 570 960 540 {lab=xn}
C {lab_pin.sym} 960 540 0 0 {name=l72 lab=xn}
N 960 630 960 660 {lab=vss}
C {lab_pin.sym} 960 660 0 0 {name=l73 lab=vss}
C {capa.sym} 0 800 0 0 {name=Coutp value=1e-14}
N 0 770 0 740 {lab=outp}
C {lab_pin.sym} 0 740 0 0 {name=l74 lab=outp}
N 0 830 0 860 {lab=vss}
C {lab_pin.sym} 0 860 0 0 {name=l75 lab=vss}
C {capa.sym} 240 800 0 0 {name=Coutn value=1e-14}
N 240 770 240 740 {lab=outn}
C {lab_pin.sym} 240 740 0 0 {name=l76 lab=outn}
N 240 830 240 860 {lab=vss}
C {lab_pin.sym} 240 860 0 0 {name=l77 lab=vss}
