# A separate run from the one that built the cell: counting in that session
# reports checks queued during construction, not what reached disk.

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
