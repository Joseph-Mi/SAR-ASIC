v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
N -70 -30 -40 -30 {lab=#net1}
N -70 60 -40 60 {lab=#net1}
N -70 -30 -70 60 {lab=#net1}
N -0 0 -0 30 {lab=out}
N -0 90 -0 110 {lab=Vss}
N -0 -90 -0 -60 {lab=Vdd}
N -90 20 -70 20 {lab=#net1}
N -0 20 10 20 {lab=out}
N 10 20 90 20 {lab=out}
N -0 -30 30 -30 {lab=Vdd}
N 30 -30 90 -30 {lab=Vdd}
N -0 60 90 60 {lab=Vss}
N -0 110 -0 120 {lab=Vss}
N 90 -50 90 -30 {lab=Vdd}
N 90 -60 90 -50 {lab=Vdd}
N 0 -60 90 -60 {lab=Vdd}
N 90 60 90 90 {lab=Vss}
N 0 90 90 90 {lab=Vss}
C {sky130_fd_pr/nfet_01v8.sym} -20 60 0 0 {name=M1
W=1
L=0.15
nf=1 
mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=nfet_01v8
spiceprefix=X
}
C {sky130_fd_pr/pfet_01v8.sym} -20 -30 0 0 {name=M2
W=1
L=0.15
nf=1
mult=1
ad="expr('int((@nf + 1)/2) * @W / @nf * 0.29')"
pd="expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)')"
as="expr('int((@nf + 2)/2) * @W / @nf * 0.29')"
ps="expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)')"
nrd="expr('0.29 / @W ')" nrs="expr('0.29 / @W ')"
sa=0 sb=0 sd=0
model=pfet_01v8
spiceprefix=X
}
C {ipin.sym} -90 20 0 0 {name=p1 lab=in}
C {iopin.sym} 0 -90 0 0 {name=p2 lab=Vdd}
C {opin.sym} 90 20 0 0 {name=p3 lab=out}
C {iopin.sym} 0 120 0 0 {name=p4 lab=Vss}
