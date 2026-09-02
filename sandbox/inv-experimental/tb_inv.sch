v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 -550 -600 250 -250 {flags=graph
y1=-1
y2=2
ypos1=0
ypos2=2
divy=6
subdivy=1
unity=1
x1=0
x2=1.8
divx=6
subdivx=1
xlabmag=1.0
ylabmag=1.0
dataset=-1
unitx=1
logx=0
logy=0
hilight_wave=0
color="4 5 6"
node="out
in
diff"}
N -260 20 -260 50 {lab=0}
N -260 -50 -260 -40 {lab=vdd}
N -190 -50 -190 -40 {lab=in}
N -190 20 -190 50 {lab=0}
N -260 50 -190 50 {lab=0}
N -190 -50 -150 -50 {lab=in}
N -260 -80 -260 -50 {lab=vdd}
N -260 -90 150 -90 {lab=vdd}
N 150 -80 150 -50 {lab=vdd}
N 150 -30 210 -30 {lab=out}
N -190 50 210 50 {lab=0}
N 210 30 210 50 {lab=0}
N 150 -10 150 50 {lab=0}
N 150 -90 150 -80 {lab=vdd}
N -260 -90 -260 -80 {lab=vdd}
C {inv.sym} 0 -30 0 0 {name=x1}
C {devices/vsource.sym} -260 -10 0 0 {name=VDD value=1.8 savecurrent=false}
C {devices/gnd.sym} -260 50 0 0 {name=l1 lab=0}
C {devices/vsource.sym} -190 -10 0 0 {name=VIN value="dc 0" savecurrent=false}
C {devices/capa.sym} 210 0 0 0 {name=C1
m=1
value=10f
footprint=1206
device="ceramic capacitor"}
C {devices/code.sym} -400 -170 0 0 {name=TT_MODELS
only_toplevel=true
format="tcleval( @value )"
value="** opencircuitdesign pdks install
.lib $::SKYWATER_MODELS/sky130.lib.spice tt

.param mc_mm_switch=0
.param mc_pr_switch=0
"
spice_ignore=false}
C {devices/code_shown.sym} -550 -90 0 0 {name=SPICE
only_toplevel=true
value="
.control
save all
dc VIN 0 1.8 0.005

let diff = v(out) - v(in)
meas dc vm when diff=0

let wn = @m.x1.xm1.msky130_fd_pr__nfet_01v8[w]
let wp = @m.x1.xm2.msky130_fd_pr__pfet_01v8[w]
let ln = @m.x1.xm1.msky130_fd_pr__nfet_01v8[l]
let lp = @m.x1.xm2.msky130_fd_pr__pfet_01v8[l]
let ratio = wp/wn

echo \\"$&wn,$&wp,$&ln,$&lp,$&ratio,1.8,tt,27,$&vm\\" >> sweep_log.csv

write tb_inv.raw
wrdata vtc.csv v(out) diff
.endc
"}
C {devices/spice_probe.sym} -260 -90 0 0 {name=p1 attrs=""}
C {devices/spice_probe.sym} -190 -50 0 0 {name=p2 attrs=""}
C {devices/spice_probe.sym} 180 -30 0 0 {name=p3 attrs=""}
C {devices/lab_wire.sym} 150 -90 0 0 {name=p4 sig_type=std_logic lab=vdd}
C {devices/lab_wire.sym} -150 -50 0 0 {name=p5 sig_type=std_logic lab=in}
C {devices/lab_wire.sym} 180 -30 0 0 {name=p6 sig_type=std_logic lab=out}
C {devices/launcher.sym} -200 -160 0 0 {name=h2
descr="Simulate"
tclcommand="xschem save; xschem netlist; xschem simulate"}
C {devices/launcher.sym} -200 -130 0 0 {name=h5
descr="Load waves"
tclcommand="xschem raw_read $netlist_dir/tb_inv.raw dc"}