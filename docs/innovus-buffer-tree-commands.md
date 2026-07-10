# Innovus buffer-tree and repeater manipulation commands

This is a project cheat sheet for the Innovus commands we use around
`deleteBufferTree`, repeater ECOs, and the Tcl wrappers in this repository.

Verification source:

- Cadence Innovus Text Command Reference, product version 25.11, local install:
  `/tools/software/cadence/ddi/25.11.001/INNOVUS251/doc/innovusTCR/`
- Innovus in-tool `man <cmd>` and `<cmd> -help`, checked with
  `/tools/software/cadence/ddi/latest/bin/innovus` version `v25.11-s102_1`
  on 2026-07-10.
- Project wrappers:
  `tcl/dbt_commands.tcl` and `tcl/dbt_manual.tcl`.

The examples use placeholder library cells such as `BUFX4` and `INVX1`.
Replace them with legal cells in the active design library. For this project,
the manual DBT presets currently use:

- ASAP7 compensation inverter: `INVxp67_ASAP7_75t_SL`, input `A`, output `Y`
- TSMCN7 compensation inverter: `INVD1BWP240H11P57PDULVT`, input `I`, output `ZN`

## 1. Native buffer-tree deletion

### `deleteBufferTree`

Purpose: remove buffer trees and back-to-back inverter pairs from the design,
excluding clock-path buffers. Innovus also calls this at the beginning of
`place_opt_design`, before global placement.

Syntax subset we use:

```tcl
deleteBufferTree \
  [-help] \
  [-excNetFile <exclude_net_file>] \
  [-footprint <footprint_name>] \
  [-preserveRoute] \
  [-selNetFile <selected_net_file> | -net {net1 net2 ...}] \
  [-verbose]
```

Important arguments:

| Argument | Meaning |
|---|---|
| `-net {net1 net2 ...}` | Process only these hierarchical nets. Mutually exclusive with `-selNetFile`. |
| `-selNetFile <file>` | Process only hierarchical nets listed in the file. Mutually exclusive with `-net`. |
| `-excNetFile <file>` | Exclude nets listed in the file. If a net is in both selected and excluded files, exclusion wins. |
| `-footprint <name>` | Remove only buffers of the specified footprint. Without this, Innovus detects one-input/one-output buffer instances whose timing arc is not `SPECIAL`. |
| `-preserveRoute` | Preserve routing for nets not impacted by the deletion. By default, Innovus removes routes after this command. |
| `-verbose` | Print more debug information, including reasons why a buffer/inverter pair was not deleted. |

Examples:

```tcl
# Run full native DBT and capture a log.
redirect deleteBufferTree.log { deleteBufferTree -verbose }

# Process only two root nets.
deleteBufferTree -net {core/u1/net_a core/u2/net_b} -verbose

# Process selected nets from a file, but keep excluded nets untouched.
deleteBufferTree \
  -selNetFile selected_nets.txt \
  -excNetFile excluded_nets.txt \
  -verbose

# Keep routing on unaffected nets where possible.
deleteBufferTree -preserveRoute -verbose
```

Recommended DEF snapshots:

```tcl
defOut -floorplan -netlist -routing -unplaced pre_deleteBufferTree.def
redirect deleteBufferTree.log { deleteBufferTree -verbose }
defOut -floorplan -netlist -routing -unplaced post_deleteBufferTree.def
```

Why `-unplaced`: DBT compensation inverters can be unplaced logical cells.
Without `-unplaced`, DEF snapshots can miss those cells.

## 2. Project wrappers for native DBT

Source:

```tcl
source /nethome/hhsiao30/deleteBufferTree/tcl/dbt_commands.tcl
```

### `dbt::delete_buffer_tree`

Purpose: thin Tcl wrapper around native `deleteBufferTree`, with optional log
redirection.

```tcl
dbt::delete_buffer_tree \
  [-verbose] \
  [-net|-nets {net1 net2 ...}] \
  [-selNetFile|-net_file <file>] \
  [-excNetFile|-exclude_net_file <file>] \
  [-footprint <name>] \
  [-preserveRoute|-preserve_route] \
  [-log <log_file>]
```

Examples:

```tcl
dbt::delete_buffer_tree -verbose -log deleteBufferTree.log

dbt::delete_buffer_tree \
  -nets {core/u1/net_a core/u2/net_b} \
  -preserve_route \
  -verbose \
  -log selected_dbt.log
```

### `dbt::write_delete_buffer_tree_script`

Purpose: generate a runnable Innovus Tcl script that performs pre/post DEF
dumping around native DBT.

```tcl
dbt::write_delete_buffer_tree_script <out_file> \
  [-pre_def <pre.def>] \
  [-post_def <post.def>] \
  [-log <deleteBufferTree.log>] \
  [-include_unplaced true|false] \
  [deleteBufferTree args...]
```

Example:

```tcl
dbt::write_delete_buffer_tree_script run_native_dbt.tcl \
  -pre_def pre_deleteBufferTree.def \
  -post_def post_deleteBufferTree.def \
  -log deleteBufferTree.log \
  -include_unplaced true \
  -verbose

source run_native_dbt.tcl
```

## 3. Add a buffer or inverter ECO

### `ecoAddRepeater`

Purpose: insert a buffer, or an inverter pair by default, on a net. It can
insert by net, by sink terminal list, at a location, near a sink/driver, or
using slack/offload modes.

Syntax subset we use:

```tcl
ecoAddRepeater \
  {-net <net_name> | -term {inst/pin ...}} \
  -cell {cell1 [cell2 ...]} \
  [-name <inst_name_or_names>] \
  [-newNetName <net_name_or_names>] \
  [-loc {x y} | -loc {x1 y1 x2 y2}] \
  [-relativeDistToSink <0.0_to_1.0>] \
  [-offLoadSlack <slack>] \
  [-offLoadAtLoc {x1a y1a x1b y1b ...}] \
  [-spreadDist <distance>] \
  [-firstSpreadDist <distance>] \
  [-spreadCount <count>] \
  [-spreadPrefix <prefix>] \
  [-radius <um>] \
  [-logicalChangeOnly] \
  [-noPlace]
```

Important arguments:

| Argument | Meaning |
|---|---|
| `-net <net>` | Insert on the named net. |
| `-term {inst/pin ...}` | Insert for selected sink terms on a common net. |
| `-cell {cell1 ...}` | Repeater master cell or list of cells. If the cell is an inverter and LEQ checking is enabled, Innovus inserts an inverter pair. |
| `-name <name>` | Base name for the inserted instance. For inverter pairs, names can be given as nested braces. |
| `-newNetName <name>` | Base name for the new net created by repeater insertion. For inverter pairs, names can be given as nested braces. |
| `-loc {x y}` | Place a buffer at a coordinate. For an inverter pair, `{x1 y1 x2 y2}` can place the two inverters separately. |
| `-relativeDistToSink <w>` | Location based on driver/sink distance. `0.1` is near the sink; `0.9` is near the driver. Manual restriction: works with one term or a one-sink net, not general multi-sink nets. |
| `-offLoadSlack <slack>` | Offload noncritical receivers below a slack threshold. Mutually exclusive with `-loc` and `-offLoadAtLoc`. |
| `-noPlace` | Make only the logical connectivity change; inserted cells are not placed. Useful for post-mask/spare-cell flows. |
| `-logicalChangeOnly` | Logical-only addition mode. |

Manual-confirmed behavior:

- If `-cell` is an inverter and `setEcoMode -LEQCheck true`, Innovus inserts a
  back-to-back inverter pair.
- If `setEcoMode -LEQCheck false`, Innovus can insert a single inverter.
- `ecoAddRepeater` returns names for the new instance/net objects. For one
  buffer, the return list is typically `{newInstName inputNet outputNet}`.

Examples:

```tcl
# Insert one buffer on a one-sink net, near the sink.
ecoAddRepeater \
  -net core/u1/net_a \
  -cell BUFX4 \
  -relativeDistToSink 0.1

# Insert one buffer on a one-sink net, near the driver.
ecoAddRepeater \
  -net core/u1/net_a \
  -cell BUFX4 \
  -relativeDistToSink 0.9

# Insert a buffer at an explicit location.
ecoAddRepeater \
  -net core/u1/net_a \
  -cell BUFX4 \
  -loc {123.0 450.0}

# Insert a buffer only for selected sinks on the same net.
ecoAddRepeater \
  -term {U1/A U2/B U3/C} \
  -cell BUFX4

# Capture the inserted instance and net names.
set r [ecoAddRepeater -net core/u1/net_a -cell BUFX4 -loc {123.0 450.0}]
set new_inst [lindex $r 0]
set input_net [lindex $r 1]
set output_net [lindex $r 2]
```

Single-inverter example for DBT-style compensation:

```tcl
# Default LEQ behavior inserts inverter pairs. Disable it for one inverter.
setEcoMode -LEQCheck false

ecoAddRepeater \
  -term {U1/A U2/B} \
  -cell INVX1 \
  -name DBT_INV_0 \
  -newNetName DBT_N_0 \
  -noPlace
```

Project wrapper:

```tcl
dbt::eco_insert_repeater \
  -net core/u1/net_a \
  -cell BUFX4 \
  -loc {123.0 450.0}

dbt::eco_insert_repeater \
  -terms {U1/A U2/B} \
  -cell INVX1 \
  -name DBT_INV_0 \
  -new_net_name DBT_N_0 \
  -no_place \
  -single_inverter true
```

## 4. ECO mode settings

### `setEcoMode`

Purpose: control behavior of interactive ECO commands such as
`ecoAddRepeater`, `ecoDeleteRepeater`, and `ecoChangeCell`.

Relevant arguments:

| Argument | Meaning |
|---|---|
| `-LEQCheck true|false` | Controls logical-equivalence behavior. `true` inserts/deletes inverter pairs for inverter ECOs. `false` allows single-inverter add/delete. Default is `true`. |
| `-honorDontTouch true|false` | Honor `dont_touch` nets/instances. Default is `true`. |
| `-honorDontUse true|false` | Honor `dontUse` cells. Default is `true`. |
| `-honorFixedNetWire true|false` | Protect fixed/cover net wires. Default is `true`. |
| `-honorFixedStatus true|false` | Protect fixed instances. Default is `true`. |
| `-honorPowerIntent true|false` | Enforce MSV/power-intent checks. Default is `true`. |
| `-refinePlace true|false` | Legalize after ECO add/change. Default is `true`; disabling can improve runtime for many changes. |
| `-batchMode true|false` | Batch many ECO operations. Exit batch mode explicitly with `false`. |
| `-prefixName <prefix>` | Prefix for ECO inserted cells. |
| `-reset` | Reset ECO mode settings to defaults. Must be first if used. |

Example:

```tcl
# Many logical ECO edits, then restore normal mode.
setEcoMode -LEQCheck false -refinePlace false -updateTiming false

ecoAddRepeater -term {U1/A} -cell INVX1 -name DBT_INV_0 -newNetName DBT_N_0 -noPlace

setEcoMode -reset
```

## 5. Delete an inserted repeater

### `ecoDeleteRepeater`

Purpose: delete a buffer or a back-to-back inverter pair and merge wires after
ECO.

Syntax subset:

```tcl
ecoDeleteRepeater \
  [-help] \
  [-logicalChangeOnly] \
  {-inst {inst1 inst2 ...} | -invPair {{inv1 inv2} {inv3 inv4} ...}}
```

Important arguments:

| Argument | Meaning |
|---|---|
| `-inst {insts}` | Delete specified buffer/inverter instances. If an inverter is specified and LEQ checking is enabled, Innovus looks for and deletes the tied back-to-back pair. |
| `-invPair {{a b} ...}` | Explicit inverter pairs to delete/evaluate. |
| `-logicalChangeOnly` | Logical-only deletion mode. |

Examples:

```tcl
# Delete one buffer.
ecoDeleteRepeater -inst U_BUF1

# Delete several repeaters.
ecoDeleteRepeater -inst {U_BUF1 U_BUF2}

# Delete an explicit inverter pair.
ecoDeleteRepeater -invPair {{U_INV_A U_INV_B}}
```

Project wrapper:

```tcl
dbt::eco_delete_repeater -insts {U_BUF1 U_BUF2}
dbt::eco_delete_repeater -inv_pair {{U_INV_A U_INV_B}}
dbt::eco_delete_repeater -insts {U_BUF1} -logical_only
```

## 6. Rule-based repeater insertion

### `addRepeaterByRule`

Purpose: insert buffers/inverters according to a rule file. This is useful for
bulk buffering driven by constraints such as max net length, radius length,
capacitance, and fanout.

Syntax subset:

```tcl
addRepeaterByRule \
  [-help] \
  [-rule <rule_file>] \
  [-nets {net1 net2 ...} | -selNet <file> | -selected] \
  [-excNet <file>] \
  [-preRoute | -postRoute | -alongRoute] \
  [-netMapping <file>] \
  [-outDir <dir>] \
  [-copyNetAttribute] \
  [-allowMixedSignal] \
  [-reportIgnoredNets <file>] \
  [-template]
```

Important arguments:

| Argument | Meaning |
|---|---|
| `-rule <file>` | Rule file listing allowed repeaters and constraints. Only cells in the rule file are inserted. |
| `-nets {nets}` | Process only listed nets. Mutually exclusive with `-selNet` and `-selected`. |
| `-selNet <file>` | Process nets listed in a file. Mutually exclusive with `-nets` and `-selected`. |
| `-excNet <file>` | Exclude nets listed in a file. |
| `-preRoute` | Pre-route insertion using different routing topologies; database should be global-routed with pre-route RC extraction. |
| `-postRoute` | Post-route insertion along detailed route with detailed RC extraction. Minimizes routing changes. |
| `-alongRoute` | Insert along route; database should be global-routed with pre-route RC extraction. |
| `-netMapping <file>` | Write original-to-new net mapping. |
| `-outDir <dir>` | Directory for detailed failure reports. |
| `-template` | Write a template rule file; other parameters are ignored. |

Manual-confirmed caution:

- `addRepeaterByRule` does not legalize newly inserted buffers. Run placement
  legalization/refinement and ECO routing as appropriate for the selected mode.

Small rule-file example:

```tcl
# repeater.rule
SetBufferMaxNetLength BUFX4 300.0
SetInverterMaxNetLength INVX1 150.0
SetDefaultMaxNetLength 100.0
SetDefaultMaxFanout 20
```

Command examples:

```tcl
# Pre-route bulk insertion for selected nets.
addRepeaterByRule \
  -rule repeater.rule \
  -preRoute \
  -nets {net_a net_b} \
  -netMapping repeater_net_map.txt \
  -outDir timingReports

# Generate a template rule file.
addRepeaterByRule -template
```

Project wrapper:

```tcl
dbt::add_repeater_by_rule \
  -rule repeater.rule \
  -pre_route \
  -nets {net_a net_b} \
  -net_mapping repeater_net_map.txt \
  -out_dir timingReports
```

## 7. DEF and log output helpers

### `defOut`

Purpose: write design information to a DEF file.

For this project, use:

```tcl
defOut -floorplan -netlist -routing -unplaced out.def
```

Relevant arguments:

| Argument | Meaning |
|---|---|
| `-floorplan` | Write floorplan data and placed standard cells. |
| `-netlist` | Write netlist/connectivity information. Manual note: use with `-unplaced` if the design has not been placed. |
| `-routing` | Write routing information to the DEF `NETS` section; implies `-netlist`. |
| `-unplaced` | Write unplaced standard cells. Required for DBT snapshots when compensation cells are unplaced. |
| `-scanChain` | Write scan-chain information if scan-chain preservation matters in your flow. |

Examples:

```tcl
defOut -floorplan -netlist -routing -unplaced pre.def
defOut -floorplan -netlist -routing -unplaced post.def
```

### `redirect`

Purpose: redirect Innovus command output to a file or variable.

Examples:

```tcl
redirect deleteBufferTree.log { deleteBufferTree -verbose }
redirect timing.txt "timeDesign -postRoute"
redirect timing.txt "timeDesign -postRoute" -append -tee
```

## 8. Low-level logical DB edits

These commands are used by `tcl/dbt_manual.tcl`. Prefer native
`deleteBufferTree` or ECO commands for production use; use these only when you
need explicit algorithm control.

### `addInst`

Purpose: add an instance.

```tcl
addInst -cell <cell_name> -inst <inst_name> \
  [-loc {x y} [-ori R0|R90|R180|R270|MX|MX90|MY|MY90]] \
  [-place_status placed|fixed|soft_fixed|unplaced|cover]
```

Manual detail: default placement status is `unplaced`. The manual also states
that the default location is the design origin if no `-loc` is given. For
DBT-style logical changes, keep the instance unplaced and verify snapshots with
DEF `-unplaced`.

Example:

```tcl
addInst -cell INVX1 -inst DBT_INV_0
```

### `addNet`

Purpose: add a logical or physical net.

```tcl
addNet <net_name>
addNet <net_name> -bus <start>:<end>
addNet <net_name> -moduleBased <verilog_module>
```

Examples:

```tcl
addNet DBT_N_0
addNet bus_net -bus 0:7
```

Implementation note: the project Tcl uses `addNet <net_name>` first and falls
back to `addNet -name <net_name>` for compatibility with observed Innovus
usage examples.

### `attachTerm`

Purpose: connect an instance terminal to a net. If the terminal is already
connected elsewhere, Innovus detaches it first and reconnects it to the new net.

```tcl
attachTerm <inst_name> <term_name> <net_name> \
  [-moduleBased <module_name>] \
  [-noNewPort] \
  [-pin <ref_inst> <ref_pin>] \
  [-port <port_name>]
```

Example:

```tcl
attachTerm DBT_INV_0 A root_net
attachTerm DBT_INV_0 Y DBT_N_0
attachTerm U_SINK A DBT_N_0
```

### `attachModulePort`

Purpose: connect a module port to a net. Use `-` as the module name for the
top module.

```tcl
attachModulePort <module_name_or_dash> <port_name> <net_name> [-noNewPort]
```

Example:

```tcl
attachModulePort - out DBT_N_0
```

### `deleteInst`

Purpose: delete logical or physical instances.

```tcl
deleteInst <inst_or_inst_list> [-honorDontTouch] [-moduleBased <module>] [-verbose]
```

Examples:

```tcl
deleteInst U_BUF1
deleteInst {U_BUF1 U_BUF2} -verbose
```

### `deleteNet`

Purpose: logically delete a net. If the net is routed, associated wire segments
are also deleted.

```tcl
deleteNet <net_name> [-bus <start>:<end>] [-moduleBased <module>]
```

Example:

```tcl
deleteNet old_buffer_output_net
```

## 9. Manual Tcl DBT algorithm

Source:

```tcl
source /nethome/hhsiao30/deleteBufferTree/tcl/dbt_manual.tcl
```

### `dbt::analyze_delete_buffer_tree`

Purpose: dry-run the project manual DBT algorithm and print/report what would
be changed.

```tcl
dbt::analyze_delete_buffer_tree \
  [-node asap7|tsmcn7] \
  [-nets {root_net1 root_net2 ...}] \
  [-verbose 0|1] \
  [-max_trees <N>]
```

Example:

```tcl
dbt::analyze_delete_buffer_tree -node asap7 -max_trees 10
```

### `dbt::manual_delete_buffer_tree`

Purpose: apply the project manual DBT algorithm in Tcl using Innovus DB editing
commands. This is for transparency and controlled experiments. For production
exactness, prefer native `deleteBufferTree`.

```tcl
dbt::manual_delete_buffer_tree \
  [-node asap7|tsmcn7] \
  [-nets {root_net1 root_net2 ...}] \
  [-dry_run 0|1] \
  [-verbose 0|1] \
  [-max_trees <N>] \
  [-new_cell <master>] \
  [-new_cell_in_pin <pin>] \
  [-new_cell_out_pin <pin>] \
  [-new_inst_prefix <prefix>] \
  [-new_net_prefix <prefix>]
```

Examples:

```tcl
# Dry-run all candidate trees using ASAP7 patterns.
dbt::manual_delete_buffer_tree -node asap7 -dry_run 1

# Apply to selected root nets only.
dbt::manual_delete_buffer_tree \
  -node asap7 \
  -nets {root_net_a root_net_b} \
  -new_inst_prefix DBT_INV_ \
  -new_net_prefix DBT_N_

defOut -floorplan -netlist -routing -unplaced post_manual_dbt.def
```

Scope limitations:

- Intended for flat, pre-CTS designs.
- Cell classification is pattern-based and uses the repo presets.
- It intentionally skips clock sinks, single-inverter special cases, and
  degenerate/island cases according to the project algorithm.

## 10. Minimal project workflows

### Workflow A: native DBT with pre/post DEF

```tcl
source /nethome/hhsiao30/deleteBufferTree/tcl/dbt_commands.tcl

dbt::write_delete_buffer_tree_script run_dbt.tcl \
  -pre_def pre_deleteBufferTree.def \
  -post_def post_deleteBufferTree.def \
  -log deleteBufferTree.log \
  -include_unplaced true \
  -verbose

source run_dbt.tcl
```

### Workflow B: targeted DBT on a few nets

```tcl
source /nethome/hhsiao30/deleteBufferTree/tcl/dbt_commands.tcl

defOut -floorplan -netlist -routing -unplaced pre_selected.def

dbt::delete_buffer_tree \
  -nets {net_a net_b net_c} \
  -verbose \
  -log selected_deleteBufferTree.log

defOut -floorplan -netlist -routing -unplaced post_selected.def
```

### Workflow C: manual DBT experiment

```tcl
source /nethome/hhsiao30/deleteBufferTree/tcl/dbt_manual.tcl

dbt::analyze_delete_buffer_tree -node asap7 -max_trees 20

dbt::manual_delete_buffer_tree \
  -node asap7 \
  -max_trees 20 \
  -new_inst_prefix DBT_INV_ \
  -new_net_prefix DBT_N_

defOut -floorplan -netlist -routing -unplaced post_manual_dbt.def
```

### Workflow D: ECO insert and then route

```tcl
setEcoMode -LEQCheck true -refinePlace true

set r [ecoAddRepeater \
  -net net_a \
  -cell BUFX4 \
  -loc {123.0 450.0}]

puts "Inserted: $r"

# Follow your normal legalization/routing flow here.
# For detailed ECO routing, this is commonly followed by ecoRoute in a routed design.
```
