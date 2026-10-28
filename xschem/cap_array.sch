v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
T {cap_array -- the binary-weighted array, 1024 units of 2 x 2 um in 11 branches.} -160 -340 0 0 0.4 0.4 {}
T {One element per branch, its multiplier the units in it. The units themselves
are the layout's (M6): a branch is 2^k identical capacitors in parallel and this
sheet carries the ratio. Each instance states a format of its own because the
PDK's symbol emits MF=, which its model does not read -- see sim/cap_array.py.} -160 -300 0 0 0.25 0.25 {}
T {bit 0
1 unit} 20 80 0 0 0.25 0.25 {}
T {bit 1
2 units} 180 80 0 0 0.25 0.25 {}
T {bit 2
4 units} 340 80 0 0 0.25 0.25 {}
T {bit 3
8 units} 500 80 0 0 0.25 0.25 {}
T {bit 4
16 units} 660 80 0 0 0.25 0.25 {}
T {bit 5
32 units} 820 80 0 0 0.25 0.25 {}
T {bit 6
64 units} 980 80 0 0 0.25 0.25 {}
T {bit 7
128 units} 1140 80 0 0 0.25 0.25 {}
T {bit 8
256 units} 1300 80 0 0 0.25 0.25 {}
T {bit 9
512 units} 1460 80 0 0 0.25 0.25 {}
T {dummy
1 unit} 1740 80 0 0 0.25 0.25 {}
N -160 -140 1720 -140 {lab=top}
N 0 -140 0 -30 {lab=top}
N 0 30 0 140 {lab=b0}
N 160 -140 160 -30 {lab=top}
N 160 30 160 140 {lab=b1}
N 320 -140 320 -30 {lab=top}
N 320 30 320 140 {lab=b2}
N 480 -140 480 -30 {lab=top}
N 480 30 480 140 {lab=b3}
N 640 -140 640 -30 {lab=top}
N 640 30 640 140 {lab=b4}
N 800 -140 800 -30 {lab=top}
N 800 30 800 140 {lab=b5}
N 960 -140 960 -30 {lab=top}
N 960 30 960 140 {lab=b6}
N 1120 -140 1120 -30 {lab=top}
N 1120 30 1120 140 {lab=b7}
N 1280 -140 1280 -30 {lab=top}
N 1280 30 1280 140 {lab=b8}
N 1440 -140 1440 -30 {lab=top}
N 1440 30 1440 140 {lab=b9}
N 1720 -140 1720 -30 {lab=top}
N 1720 30 1720 140 {lab=bd}
C {iopin.sym} -160 -140 2 0 {name=ptop lab=top}
C {sky130_fd_pr/cap_mim_m3_1.sym} 0 0 0 0 {name=u0 model=cap_mim_m3_1 W=2 L=2 MF=1 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 0 140 0 0 {name=p0 lab=b0}
C {sky130_fd_pr/cap_mim_m3_1.sym} 160 0 0 0 {name=u1 model=cap_mim_m3_1 W=2 L=2 MF=2 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 160 140 0 0 {name=p1 lab=b1}
C {sky130_fd_pr/cap_mim_m3_1.sym} 320 0 0 0 {name=u2 model=cap_mim_m3_1 W=2 L=2 MF=4 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 320 140 0 0 {name=p2 lab=b2}
C {sky130_fd_pr/cap_mim_m3_1.sym} 480 0 0 0 {name=u3 model=cap_mim_m3_1 W=2 L=2 MF=8 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 480 140 0 0 {name=p3 lab=b3}
C {sky130_fd_pr/cap_mim_m3_1.sym} 640 0 0 0 {name=u4 model=cap_mim_m3_1 W=2 L=2 MF=16 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 640 140 0 0 {name=p4 lab=b4}
C {sky130_fd_pr/cap_mim_m3_1.sym} 800 0 0 0 {name=u5 model=cap_mim_m3_1 W=2 L=2 MF=32 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 800 140 0 0 {name=p5 lab=b5}
C {sky130_fd_pr/cap_mim_m3_1.sym} 960 0 0 0 {name=u6 model=cap_mim_m3_1 W=2 L=2 MF=64 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 960 140 0 0 {name=p6 lab=b6}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1120 0 0 0 {name=u7 model=cap_mim_m3_1 W=2 L=2 MF=128 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 1120 140 0 0 {name=p7 lab=b7}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1280 0 0 0 {name=u8 model=cap_mim_m3_1 W=2 L=2 MF=256 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 1280 140 0 0 {name=p8 lab=b8}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1440 0 0 0 {name=u9 model=cap_mim_m3_1 W=2 L=2 MF=512 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 1440 140 0 0 {name=p9 lab=b9}
C {sky130_fd_pr/cap_mim_m3_1.sym} 1720 0 0 0 {name=ud model=cap_mim_m3_1 W=2 L=2 MF=1 spiceprefix=X format="@spiceprefix@name @pinlist sky130_fd_pr__@model w=@W l=@L mult=@MF m=@MF"}
C {iopin.sym} 1720 140 0 0 {name=p10 lab=bd}
