# Coordinates given to magic are lambda; coordinates magic reports are internal
# units, twice as fine. Everything here is internal, converted on the way out.

set DY 800

set N_HALF_Y 226
set P_HALF_Y 231
set HALF_X   158

set N_B  {-153 -249  153 -203}
set N_D  { -67 -131  -21   69}
set N_S  {  21 -131   67   69}
set N_G  { -29  101   29  147}
set P_G  { -29 -151   29 -105}
set P_D  { -67  -64  -21  136}
set P_S  {  21  -64   67  136}
set P_B  {-153  208  153  254}

proc ibox {x1 y1 x2 y2} {
    box [expr {$x1 / 2.0}] [expr {$y1 / 2.0}] [expr {$x2 / 2.0}] [expr {$y2 / 2.0}]
}
proc strap {x1 y1 x2 y2} {
    ibox $x1 $y1 $x2 $y2
    paint metal1
}
proc pin {name x y} {
    ibox $x $y $x $y
    label $name c metal1
    port make
}
proc rel {pad dy} {
    lassign $pad x1 y1 x2 y2
    list $x1 [expr {$y1 + $dy}] $x2 [expr {$y2 + $dy}]
}

proc place {gencell inst ox oy hx hy params} {
    ibox [expr {$ox - $hx}] [expr {$oy - $hy}] [expr {$ox - $hx}] [expr {$oy - $hy}]
    eval [list magic::gencell $gencell $inst] $params
    select cell $inst
    lassign [box values] x1 y1 x2 y2
    set cx [expr {($x1 + $x2) / 2}]
    set cy [expr {($y1 + $y2) / 2}]
    if {$cx != $ox || $cy != $oy} {
        error "$inst origin landed at $cx $cy, wanted $ox $oy"
    }
    select clear
}

file delete -force inv.mag
foreach f [glob -nocomplain sky130_fd_pr__*fet_01v8_*.mag] { file delete -force $f }

drc off
load inv -silent

place sky130::sky130_fd_pr__nfet_01v8 nmos0 0 0 $HALF_X $N_HALF_Y \
    {w 1 l 0.15 nf 1 guard 1 full_metal 0 viagb 100 topc 1 botc 0}
place sky130::sky130_fd_pr__pfet_01v8 pmos0 0 $DY $HALF_X $P_HALF_Y \
    {w 1 l 0.15 nf 1 guard 1 full_metal 0 viagt 100 topc 0 botc 1}

lassign $N_G ngx1 ngy1 ngx2 ngy2
lassign $N_D ndx1 ndy1 ndx2 ndy2
lassign $N_S nsx1 nsy1 nsx2 nsy2
lassign $N_B nbx1 nby1 nbx2 nby2
lassign [rel $P_G $DY] pgx1 pgy1 pgx2 pgy2
lassign [rel $P_D $DY] pdx1 pdy1 pdx2 pdy2
lassign [rel $P_S $DY] psx1 psy1 psx2 psy2
lassign [rel $P_B $DY] pbx1 pby1 pbx2 pby2

strap $ngx1 $ngy1 $ngx2 $pgy2

set OUT_X1 -120
set OUT_X2  -92
set STUB 46
strap $OUT_X1 [expr {$ndy2 - $STUB}] $ndx2 $ndy2
strap $OUT_X1 [expr {$ndy2 - $STUB}] $OUT_X2 [expr {$pdy1 + $STUB + 24}]
strap $OUT_X1 [expr {$pdy1 + 24}] $pdx2 [expr {$pdy1 + $STUB + 24}]

strap $nsx1 $nby1 $nsx2 [expr {$nsy1 + 12}]
strap $psx1 [expr {$psy2 - 12}] $psx2 $pby2

pin in  0 [expr {($ngy2 + $pgy1) / 2}]
pin out [expr {($OUT_X1 + $OUT_X2) / 2}] [expr {($ndy2 + $pdy1) / 2}]
# A label attaches to empty space unless the metal beneath it belongs to this
# cell rather than to a child.
pin Vss [expr {($nsx1 + $nsx2) / 2}] [expr {($nby1 + $nby2) / 2}]
pin Vdd [expr {($psx1 + $psx2) / 2}] [expr {($psy2 + $pby2) / 2}]

writeall force
puts "WROTE [cellname list allcells]"
quit -noprompt
