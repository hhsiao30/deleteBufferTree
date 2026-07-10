# Innovus buffer-tree Tcl commands

This directory adds Tcl-side commands for the `deleteBufferTree` work.

## 1. Native Innovus command

The verified Cadence command is:

```tcl
deleteBufferTree -verbose
```

Useful variants:

```tcl
# Only selected root nets
deleteBufferTree -net {net1 net2 net3} -verbose

# Nets from a file
deleteBufferTree -selNetFile selected_nets.txt -verbose

# Exclude nets from a file
deleteBufferTree -excNetFile excluded_nets.txt -verbose

# Preserve unaffected routes where possible
deleteBufferTree -preserveRoute -verbose
```

The wrapper in `dbt_commands.tcl` emits/runs the same command:

```tcl
source /nethome/hhsiao30/deleteBufferTree/tcl/dbt_commands.tcl

dbt::delete_buffer_tree -verbose -log deleteBufferTree.log

dbt::write_delete_buffer_tree_script run_deleteBufferTree.tcl \
  -pre_def pre_deleteBufferTree.def \
  -post_def post_deleteBufferTree.def \
  -log deleteBufferTree.log \
  -verbose
```

For DEF comparison, keep `-unplaced` in `defOut`; new compensation inverters are unplaced.

## 2. Manual Tcl algorithm implementation

`dbt_manual.tcl` implements the flat pre-CTS algorithm in Innovus Tcl:

```tcl
source /nethome/hhsiao30/deleteBufferTree/tcl/dbt_manual.tcl

# Dry-run report
dbt::analyze_delete_buffer_tree -node asap7

# Apply the transform
dbt::manual_delete_buffer_tree -node asap7

defOut -floorplan -netlist -routing -unplaced post_manual_dbt.def
```

Supported presets:

```tcl
dbt::manual_delete_buffer_tree -node asap7
dbt::manual_delete_buffer_tree -node tsmcn7
```

Selective run:

```tcl
dbt::manual_delete_buffer_tree -node asap7 -nets {root_net_a root_net_b}
```

Important scope:

- Intended for flat, pre-CTS netlists.
- Classification is pattern-based, matching the current Python presets.
- For exact production behavior, prefer native `deleteBufferTree`; the manual implementation is primarily for transparent algorithm control and experimentation.

## 3. Insert/delete buffer or inverter ECO commands

Documented Innovus commands from the installed 25.11 command reference:

```tcl
# Insert a buffer on a net
ecoAddRepeater -net myNet -cell BUFX4 -relativeDistToSink 0.5

# Insert at a location
ecoAddRepeater -net myNet -cell BUFX4 -loc {123.0 450.0}

# Insert only for selected sink terms on a common net
ecoAddRepeater -term {U1/A U2/B U3/C} -cell BUFX4

# Delete one or more repeaters
ecoDeleteRepeater -inst {U_BUF1 U_BUF2}

# Rule-based bulk insertion before route
addRepeaterByRule -rule repeater.rule -preRoute -nets {net1 net2}
```

For a single compensation inverter, disable the default inverter-pair LEQ behavior:

```tcl
setEcoMode -LEQCheck false
ecoAddRepeater -term {U1/A U2/B} -cell INVX1
```

The wrapper equivalents:

```tcl
dbt::eco_insert_repeater -net myNet -cell BUFX4 -relative_dist_to_sink 0.5
dbt::eco_insert_repeater -terms {U1/A U2/B} -cell INVX1 -single_inverter true
dbt::eco_delete_repeater -insts {U_BUF1 U_BUF2}
dbt::add_repeater_by_rule -rule repeater.rule -pre_route -nets {net1 net2}
```

## 4. Low-level commands used by the manual implementation

The manual Tcl algorithm uses these Innovus DB-editing primitives:

```tcl
addInst -cell <cell> -inst <inst>
addNet <net>
attachTerm <inst> <pin> <net>
attachModulePort - <top_port> <net>
deleteInst {inst1 inst2}
deleteNet <net>
```

These are lower-level than `deleteBufferTree`; use them when you need custom behavior.
