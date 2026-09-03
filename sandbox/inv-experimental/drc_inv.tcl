# Checks the written layout. Deliberately a separate magic run: counting in
# the session that built the cell reports checks queued during construction
# rather than the state of what reached disk.
#
#   magic -dnull -noconsole drc_inv.tcl

drc on
drc euclidean on
load inv
drc check
drc catchup
puts "DRC_TOTAL=[drc list count total]"
foreach {rule boxes} [drc listall why] {
    puts "RULE: $rule"
    foreach b $boxes { puts "    $b" }
}
quit -noprompt
