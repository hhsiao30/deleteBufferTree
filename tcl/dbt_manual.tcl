# dbt_manual.tcl -- flat-netlist Tcl implementation of the verified DBT rule.
#
# This is intentionally scoped to flat pre-CTS designs, matching the validated
# Python tool scope in this repository. For production exactness, the native
# Innovus command remains:
#     deleteBufferTree -verbose
#
# The manual path exists to make the algorithm explicit in Tcl and to let you
# inspect or selectively apply the transform.

if {[file exists [file join [file dirname [info script]] dbt_commands.tcl]]} {
    source [file join [file dirname [info script]] dbt_commands.tcl]
}

namespace eval ::dbt {
    variable buf_patterns
    variable inv_patterns
    variable in_pins
    variable out_pins
    variable clock_pins
    variable new_cell
    variable new_cell_in_pin
    variable new_cell_out_pin
    variable new_inst_prefix
    variable new_net_prefix
}

proc ::dbt::use_preset {node} {
    variable buf_patterns
    variable inv_patterns
    variable in_pins
    variable out_pins
    variable clock_pins
    variable new_cell
    variable new_cell_in_pin
    variable new_cell_out_pin
    variable new_inst_prefix
    variable new_net_prefix

    set new_inst_prefix DBT_
    set new_net_prefix DBT_N_

    switch -- $node {
        asap7 {
            set buf_patterns {^BUFx ^HB[0-9] ^CKBUF}
            set inv_patterns {^INVx ^CKINV}
            set in_pins {A}
            set out_pins {Y}
            set clock_pins {CLK}
            set new_cell INVxp67_ASAP7_75t_SL
            set new_cell_in_pin A
            set new_cell_out_pin Y
        }
        tsmcn7 {
            set buf_patterns {^BUFFD ^CKBD ^BUFFSKRD ^BUFFSKFD ^DCCKBD}
            set inv_patterns {^INVD ^CKND[0-9]+BWP ^CKNTWBD ^INVSKRD ^INVSKFD ^DCCKNTWBD ^INVPADD ^CKNTWAD}
            set in_pins {I}
            set out_pins {Z ZN}
            set clock_pins {CLK CP}
            set new_cell INVD1BWP240H11P57PDULVT
            set new_cell_in_pin I
            set new_cell_out_pin ZN
        }
        default {
            error "unknown DBT preset '$node'; expected asap7 or tsmcn7"
        }
    }
}

proc ::dbt::classify_cell {cell} {
    variable buf_patterns
    variable inv_patterns
    foreach p $inv_patterns {
        if {[regexp -- $p $cell]} {
            return INV
        }
    }
    foreach p $buf_patterns {
        if {[regexp -- $p $cell]} {
            return BUF
        }
    }
    return ""
}

proc ::dbt::is_bi_in_pin {pin} {
    variable in_pins
    return [expr {[lsearch -exact $in_pins $pin] >= 0}]
}

proc ::dbt::is_bi_out_pin {pin} {
    variable out_pins
    return [expr {[lsearch -exact $out_pins $pin] >= 0}]
}

proc ::dbt::is_clock_pin {pin} {
    variable clock_pins
    return [expr {[lsearch -exact $clock_pins $pin] >= 0}]
}

proc ::dbt::_clean_db_value {v} {
    if {$v eq "0x0"} {
        return ""
    }
    return $v
}

proc ::dbt::dbget {query} {
    if {[catch {set v [uplevel #0 [list dbGet -e $query]]}]} {
        return ""
    }
    return [::dbt::_clean_db_value $v]
}

proc ::dbt::dbattr {ptr attrs} {
    foreach a $attrs {
        set v [::dbt::dbget "${ptr}.${a}"]
        if {$v ne ""} {
            return [lindex $v 0]
        }
    }
    return ""
}

proc ::dbt::net_ptr {net_name} {
    foreach cmd [list \
        [list dbGet -e top.nets.name $net_name -p] \
        [list dbGet -e top.nets.name -p $net_name] \
        [list dbGet -e -p top.nets.name $net_name]] {
        if {[catch {set ps [uplevel #0 $cmd]}]} {
            continue
        }
        foreach p [::dbt::_clean_db_value $ps] {
            if {$p eq ""} {
                continue
            }
            if {![catch {set nm [uplevel #0 [list dbGet -e ${p}.name]]}] && $nm eq $net_name} {
                return $p
            }
        }
    }
    return ""
}

proc ::dbt::inst_ptr {inst_name} {
    foreach cmd [list \
        [list dbGet -e top.insts.name $inst_name -p] \
        [list dbGet -e top.insts.name -p $inst_name] \
        [list dbGet -e -p top.insts.name $inst_name]] {
        if {[catch {set ps [uplevel #0 $cmd]}]} {
            continue
        }
        foreach p [::dbt::_clean_db_value $ps] {
            if {$p eq ""} {
                continue
            }
            if {![catch {set nm [uplevel #0 [list dbGet -e ${p}.name]]}] && $nm eq $inst_name} {
                return $p
            }
        }
    }
    return ""
}

proc ::dbt::net_terms {net_name} {
    set np [::dbt::net_ptr $net_name]
    if {$np eq ""} {
        return {}
    }
    set terms [::dbt::dbget "${np}.allTerms"]
    if {$terms eq ""} {
        set terms [concat [::dbt::dbget "${np}.instTerms"] [::dbt::dbget "${np}.terms"]]
    }
    return $terms
}

proc ::dbt::term_tuple {term_ptr} {
    set obj_type [::dbt::dbattr $term_ptr {objType}]
    if {$obj_type eq "instTerm"} {
        set inst [::dbt::dbattr $term_ptr {inst.name hInst.name}]
        # Legacy Innovus dbGet instTerm objects reliably expose the full
        # instance/pin string through .name.  Do not probe Common-UI-only
        # attributes here; failed dbGet probes print noisy IMPDBTCL messages.
        set pin [::dbt::dbattr $term_ptr {name}]
        if {[string first "/" $pin] >= 0} {
            set prefix "${inst}/"
            if {[string first $prefix $pin] == 0} {
                set pin [string range $pin [string length $prefix] end]
            } else {
                set pin [lindex [split $pin /] end]
            }
        }
        return [list INST $inst $pin]
    }

    set port [::dbt::dbattr $term_ptr {name}]
    if {[string first "/" $port] >= 0} {
        set port [lindex [split $port /] end]
    }
    return [list PORT $port $port]
}

proc ::dbt::term_net_name {term_ptr} {
    return [::dbt::dbattr $term_ptr {net.name net_name}]
}

proc ::dbt::attach_tuple_to_net {tuple net_name} {
    set kind [lindex $tuple 0]
    set obj  [lindex $tuple 1]
    set pin  [lindex $tuple 2]
    if {$kind eq "PORT"} {
        return [uplevel #0 [list attachModulePort - $obj $net_name]]
    }
    return [uplevel #0 [list attachTerm $obj $pin $net_name]]
}

proc ::dbt::tuple_is_member_input {tuple member_set_name} {
    upvar 1 $member_set_name member_set
    if {[lindex $tuple 0] ne "INST"} {
        return 0
    }
    set inst [lindex $tuple 1]
    set pin  [lindex $tuple 2]
    return [expr {[info exists member_set($inst)] && [::dbt::is_bi_in_pin $pin]}]
}

proc ::dbt::tuple_is_inst_output {tuple inst} {
    if {[lindex $tuple 0] ne "INST"} {
        return 0
    }
    return [expr {[lindex $tuple 1] eq $inst && [::dbt::is_bi_out_pin [lindex $tuple 2]]}]
}

proc ::dbt::tuple_is_clock_sink {tuple} {
    if {[lindex $tuple 0] ne "INST"} {
        return 0
    }
    return [::dbt::is_clock_pin [lindex $tuple 2]]
}

proc ::dbt::ensure_net {net_name} {
    if {[::dbt::net_ptr $net_name] ne ""} {
        return
    }
    if {[catch {uplevel #0 [list addNet $net_name]} err]} {
        uplevel #0 [list addNet -name $net_name]
    }
}

proc ::dbt::ensure_inst {inst_name cell} {
    if {[::dbt::inst_ptr $inst_name] ne ""} {
        error "instance '$inst_name' already exists"
    }
    # With no -loc, addInst creates an unplaced logical instance. This is the
    # DBT compensation-inverter style expected before placement.
    uplevel #0 [list addInst -cell $cell -inst $inst_name]
}

proc ::dbt::delete_inst_list {insts} {
    if {[llength $insts] == 0} {
        return
    }
    uplevel #0 [list deleteInst $insts]
}

proc ::dbt::delete_net_if_exists {net_name} {
    if {$net_name eq "" || [::dbt::net_ptr $net_name] eq ""} {
        return
    }
    catch {uplevel #0 [list deleteNet $net_name]}
}

proc ::dbt::_parse_manual_args {args} {
    set opts [dict create \
        -node asap7 \
        -nets {} \
        -dry_run 0 \
        -verbose 1 \
        -max_trees 0 \
        -new_cell "" \
        -new_cell_in_pin "" \
        -new_cell_out_pin "" \
        -new_inst_prefix "" \
        -new_net_prefix ""]

    set i 0
    while {$i < [llength $args]} {
        set a [lindex $args $i]
        if {![dict exists $opts $a]} {
            error "unknown manual_delete_buffer_tree option '$a'"
        }
        incr i
        if {$i >= [llength $args]} {
            error "$a requires a value"
        }
        dict set opts $a [lindex $args $i]
        incr i
    }
    return $opts
}

proc ::dbt::manual_delete_buffer_tree {args} {
    variable new_cell
    variable new_cell_in_pin
    variable new_cell_out_pin
    variable new_inst_prefix
    variable new_net_prefix

    set opts [::dbt::_parse_manual_args {*}$args]
    ::dbt::use_preset [dict get $opts -node]
    foreach key {-new_cell -new_cell_in_pin -new_cell_out_pin -new_inst_prefix -new_net_prefix} {
        set val [dict get $opts $key]
        if {$val ne ""} {
            set var [string range $key 1 end]
            set ::dbt::$var $val
        }
    }

    set dry_run [::dbt::_bool [dict get $opts -dry_run]]
    set verbose [::dbt::_bool [dict get $opts -verbose]]
    set selected_roots [dict get $opts -nets]
    set max_trees [dict get $opts -max_trees]

    array set kind {}
    array set in_net {}
    array set out_net {}
    array set bi_loads {}
    array set bi_driver {}
    array set port_net_of {}

    set degenerate 0
    foreach inst_ptr [::dbt::dbget top.insts] {
        set inst [::dbt::dbattr $inst_ptr {name}]
        set cell [::dbt::dbattr $inst_ptr {cell.name base_cell.name}]
        set k [::dbt::classify_cell $cell]
        if {$k eq ""} {
            continue
        }
        set kind($inst) $k
        foreach term [::dbt::dbget "${inst_ptr}.instTerms"] {
            set tuple [::dbt::term_tuple $term]
            set pin [lindex $tuple 2]
            set net [::dbt::term_net_name $term]
            if {$net eq ""} {
                continue
            }
            if {[::dbt::is_bi_in_pin $pin]} {
                set in_net($inst) $net
            } elseif {[::dbt::is_bi_out_pin $pin]} {
                set out_net($inst) $net
            }
        }
    }

    foreach inst [array names kind] {
        if {![info exists in_net($inst)] || ![info exists out_net($inst)]} {
            unset kind($inst)
            catch {unset in_net($inst)}
            catch {unset out_net($inst)}
            incr degenerate
            continue
        }
        lappend bi_loads($in_net($inst)) $inst
        set bi_driver($out_net($inst)) $inst
    }

    foreach term_ptr [::dbt::dbget top.terms] {
        set p [::dbt::dbattr $term_ptr {name}]
        set n [::dbt::term_net_name $term_ptr]
        if {$p ne "" && $n ne ""} {
            set port_net_of($n) $p
        }
    }

    set trees 0
    set removed_count 0
    set inserted_count 0
    set skipped_single_inv 0
    set skipped_clock 0
    set skipped_island 0
    set counter 0

    set root_nets [array names bi_loads]
    foreach R $root_nets {
        if {[info exists bi_driver($R)]} {
            continue
        }
        if {[llength $selected_roots] > 0 && [lsearch -exact $selected_roots $R] < 0} {
            continue
        }
        if {$max_trees > 0 && $trees >= $max_trees} {
            break
        }

        array unset seen
        array unset member_set
        set members {}
        set q {}
        foreach b $bi_loads($R) {
            lappend q [list $b 0]
        }
        while {[llength $q] > 0} {
            set item [lindex $q 0]
            set q [lrange $q 1 end]
            set inst [lindex $item 0]
            set par_above [lindex $item 1]
            if {[info exists seen($inst)] || ![info exists kind($inst)]} {
                continue
            }
            set seen($inst) 1
            set par [expr {$par_above + ($kind($inst) eq "INV" ? 1 : 0)}]
            lappend members [list $inst $par]
            set member_set($inst) 1
            if {[info exists bi_loads($out_net($inst))]} {
                foreach child $bi_loads($out_net($inst)) {
                    lappend q [list $child $par]
                }
            }
        }
        if {[llength $members] == 0} {
            continue
        }
        incr trees

        set tree_has_sink 0
        foreach item $members {
            set inst [lindex $item 0]
            foreach term [::dbt::net_terms $out_net($inst)] {
                set tuple [::dbt::term_tuple $term]
                if {[::dbt::tuple_is_inst_output $tuple $inst]} {
                    continue
                }
                if {[::dbt::tuple_is_member_input $tuple member_set]} {
                    continue
                }
                set tree_has_sink 1
                break
            }
            if {$tree_has_sink} {
                break
            }
        }

        set root_all_member_inputs 1
        foreach term [::dbt::net_terms $R] {
            set tuple [::dbt::term_tuple $term]
            if {![::dbt::tuple_is_member_input $tuple member_set]} {
                set root_all_member_inputs 0
                break
            }
        }
        if {!$tree_has_sink && $root_all_member_inputs} {
            incr skipped_island
            if {$verbose} { puts "DBT skip island root=$R members=[llength $members]" }
            continue
        }

        if {[llength $members] == 1} {
            set only [lindex [lindex $members 0] 0]
            if {$kind($only) eq "INV" && $tree_has_sink} {
                incr skipped_single_inv
                if {$verbose} { puts "DBT skip single INV root=$R inst=$only" }
                continue
            }
        }

        set hit_clock 0
        foreach term [::dbt::net_terms $R] {
            if {[::dbt::tuple_is_clock_sink [::dbt::term_tuple $term]]} {
                set hit_clock 1
                break
            }
        }
        foreach item $members {
            if {$hit_clock} {
                break
            }
            set inst [lindex $item 0]
            foreach term [::dbt::net_terms $out_net($inst)] {
                set tuple [::dbt::term_tuple $term]
                if {![info exists member_set([lindex $tuple 1])] && [::dbt::tuple_is_clock_sink $tuple]} {
                    set hit_clock 1
                    break
                }
            }
        }
        if {$hit_clock} {
            incr skipped_clock
            if {$verbose} { puts "DBT skip clock root=$R members=[llength $members]" }
            continue
        }

        set even_sinks {}
        set odd_sinks {}
        set even_port_nets {}
        set odd_port_nets {}
        set old_output_nets {}
        foreach item $members {
            set inst [lindex $item 0]
            set par [lindex $item 1]
            set onet $out_net($inst)
            lappend old_output_nets $onet
            set onet_is_port [info exists port_net_of($onet)]
            foreach term [::dbt::net_terms $onet] {
                set tuple [::dbt::term_tuple $term]
                if {[::dbt::tuple_is_inst_output $tuple $inst]} {
                    continue
                }
                if {[::dbt::tuple_is_member_input $tuple member_set]} {
                    continue
                }
                if {$par % 2} {
                    lappend odd_sinks $tuple
                    if {$onet_is_port && [lindex $tuple 0] eq "PORT"} {
                        lappend odd_port_nets $onet
                    }
                } else {
                    lappend even_sinks $tuple
                    if {$onet_is_port && [lindex $tuple 0] eq "PORT"} {
                        lappend even_port_nets $onet
                    }
                }
            }
        }

        set root_keep $R
        if {[llength $even_port_nets] > 0} {
            set root_keep [lindex $even_port_nets 0]
        }

        if {$verbose || $dry_run} {
            puts "DBT tree root=$R keep=$root_keep members=[llength $members] even=[llength $even_sinks] odd=[llength $odd_sinks]"
        }
        if {$dry_run} {
            continue
        }

        # If a port output net must survive, move every non-member term from the
        # root net onto that surviving net. This is equivalent to the Python
        # DEF-side "rename root to port net" rule.
        if {$root_keep ne $R} {
            ::dbt::ensure_net $root_keep
            foreach term [::dbt::net_terms $R] {
                set tuple [::dbt::term_tuple $term]
                if {![::dbt::tuple_is_member_input $tuple member_set]} {
                    ::dbt::attach_tuple_to_net $tuple $root_keep
                }
            }
        }

        foreach tuple $even_sinks {
            ::dbt::attach_tuple_to_net $tuple $root_keep
        }

        set inserted_inst ""
        set odd_net ""
        if {[llength $odd_sinks] > 0} {
            set inserted_inst "${new_inst_prefix}${counter}"
            if {[llength $odd_port_nets] > 0} {
                set odd_net [lindex $odd_port_nets 0]
            } else {
                set odd_net "${new_net_prefix}${counter}"
            }
            incr counter
            ::dbt::ensure_net $odd_net
            ::dbt::ensure_inst $inserted_inst $new_cell
            ::dbt::attach_tuple_to_net [list INST $inserted_inst $new_cell_in_pin] $root_keep
            ::dbt::attach_tuple_to_net [list INST $inserted_inst $new_cell_out_pin] $odd_net
            foreach tuple $odd_sinks {
                ::dbt::attach_tuple_to_net $tuple $odd_net
            }
            incr inserted_count
        }

        set to_delete {}
        foreach item $members {
            lappend to_delete [lindex $item 0]
        }
        ::dbt::delete_inst_list $to_delete
        incr removed_count [llength $to_delete]

        foreach n [lsort -unique $old_output_nets] {
            if {$n ne $root_keep && $n ne $odd_net} {
                ::dbt::delete_net_if_exists $n
            }
        }
        if {$root_keep ne $R} {
            ::dbt::delete_net_if_exists $R
        }
    }

    set stats [dict create \
        trees $trees \
        removed $removed_count \
        inserted $inserted_count \
        skipped_single_inv $skipped_single_inv \
        skipped_clock $skipped_clock \
        skipped_island $skipped_island \
        degenerate $degenerate]
    puts "DBT manual: $stats"
    return $stats
}

proc ::dbt::analyze_delete_buffer_tree {args} {
    return [::dbt::manual_delete_buffer_tree -dry_run 1 {*}$args]
}
