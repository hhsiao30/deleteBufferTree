# Native Innovus buffer-tree and repeater manipulation commands

This document lists only the key native Cadence Innovus commands relevant to
deleting buffer trees and inserting/deleting repeaters.

Verified against:

- Cadence Innovus Text Command Reference, product version 25.11:
  `/tools/software/cadence/ddi/25.11.001/INNOVUS251/doc/innovusTCR/`
- Innovus in-tool `man <cmd>` and `<cmd> -help`
- Installed Innovus binary checked on 2026-07-10:
  `/tools/software/cadence/ddi/latest/bin/innovus`, version `v25.11-s102_1`

The example library cells, such as `BUFX4` and `INVX1`, are placeholders.
Use legal cells from the active design library.

## 1. `deleteBufferTree`

Purpose: remove buffers, except clock-path buffers, and back-to-back inverter
pairs from the design. Innovus also calls this at the beginning of
`place_opt_design`, before global placement.

Syntax:

```tcl
deleteBufferTree \
  [-help] \
  [-excNetFile <excFileName>] \
  [-footprint <footPrintName>] \
  [-preserveRoute] \
  [-selNetFile <selFileName> | -net {list_of_nets}] \
  [-verbose]
```

Arguments:

| Argument | Description |
|---|---|
| `-help` | Print command usage and parameter type/default information. |
| `-excNetFile <file>` | File containing hierarchical nets to exclude from buffer removal. If a net is both selected and excluded, exclusion wins. |
| `-footprint <footprint>` | Remove buffers of a specified footprint. If omitted, Innovus removes one-input/one-output buffer instances whose timing arc is not `SPECIAL`. |
| `-net {net1 net2 ...}` | Process only the listed hierarchical nets. Mutually exclusive with `-selNetFile`. |
| `-selNetFile <file>` | File containing hierarchical nets to include. Mutually exclusive with `-net`. |
| `-preserveRoute` | Preserve routing on nets not impacted by the buffer/inverter deletion. By default, Innovus removes routes after running this command. |
| `-verbose` | Print extra debug messages, such as reasons a buffer or inverter pair was not deleted. |

Examples:

```tcl
# Delete all eligible non-clock buffer trees and inverter pairs.
deleteBufferTree -verbose

# Delete buffer trees only on selected nets.
deleteBufferTree -net {top/u1/net_a top/u2/net_b} -verbose

# Use selected/excluded net files.
deleteBufferTree \
  -selNetFile selected_nets.txt \
  -excNetFile excluded_nets.txt \
  -verbose

# Preserve routes on unaffected nets.
deleteBufferTree -preserveRoute -verbose

# Remove only buffers of a specific footprint.
deleteBufferTree -footprint B_1P -verbose
```

## 2. `ecoAddRepeater`

Purpose: add a buffer, or by default a pair of inverters when the specified
cell is an inverter, on a net. The command can insert by net, by sink terminal
list, at explicit coordinates, by relative driver/sink distance, or by
slack/offload criteria.

Common syntax subset:

```tcl
ecoAddRepeater \
  {-net <netName> | -term {term1 term2 ...}} \
  -cell {cell1 [cell2 ...]} \
  [-name <instName>] \
  [-newNetName <netName>] \
  [-loc {x y} | -loc {x1 y1 x2 y2}] \
  [-relativeDistToSink <sinkWeight>] \
  [-offLoadSlack <slack>] \
  [-offLoadAtLoc {x1a y1a x1b y1b ...}] \
  [-spreadDist <distance>] \
  [-firstSpreadDist <distance>] \
  [-spreadCount <number>] \
  [-spreadPrefix <prefix>] \
  [-radius <um>] \
  [-logicalChangeOnly] \
  [-noPlace]
```

Arguments:

| Argument | Description |
|---|---|
| `-help` | Print command usage. |
| `-net <netName>` | Net where the repeater is inserted. |
| `-term {term1 term2 ...}` | Sink terminal list. Terms must be connected to a common net. If `-term` is omitted, all terms of the net are buffered. |
| `-cell {cell1 cell2 ...}` | Repeater master cell or list of cells. If an inverter is specified and `setEcoMode -LEQCheck true`, Innovus inserts an inverter pair. |
| `-name <instName>` | Base name for inserted instance. For inverter pairs, two names can be specified with nested braces, for example `-name {{inv0 inv1}}`. |
| `-newNetName <netName>` | Base name for the new net created by insertion. For inverter pairs, two names can be specified with nested braces. |
| `-loc {x y}` | Location for a buffer. For an inverter pair, `{x1 y1 x2 y2}` places the two inverters separately. |
| `-bufOrient {R0|R90|R180|R270|MX|MX90|MY|MY90}` | Legalized orientation. Requires `-loc`. |
| `-relativeDistToSink <sinkWeight>` | Value from 0 to 1. `0.1` places near the sink; `0.9` places near the driver. Works only with one term or a one-sink net. |
| `-offLoadSlack <slack>` | Offload noncritical receivers selected by slack. Mutually exclusive with `-loc` and `-offLoadAtLoc`. |
| `-offLoadAtLoc {coords...}` | Insert at locations to drive sinks downstream from those locations. |
| `-spreadDist <distance>` | Add repeaters every specified distance from the driver. |
| `-firstSpreadDist <distance>` | Distance from driver for the first repeated insertion. Requires `-spreadDist`. |
| `-spreadCount <number>` | Number of repeaters to add. |
| `-spreadPrefix <prefix>` | Prefix for new instances and nets created by spread buffering. |
| `-radius <um>` | Radius in which added instances may move. Requires `-loc`, `-relativeDistToSink`, or `-offLoadAtLoc`. |
| `-logicalChangeOnly` | Perform logical-only addition. |
| `-noPlace` | Do not place inserted cells; only logical connectivity is changed. Useful in post-mask/spare-cell style ECOs. |

Manual-confirmed behavior:

- `ecoAddRepeater` cuts wires by default.
- If `-cell` is an inverter and `setEcoMode -LEQCheck true`, Innovus adds a
  back-to-back inverter pair.
- If `setEcoMode -LEQCheck false`, Innovus can add a single inverter.
- The command can return new instance/net names. For one buffer, the return
  list is typically `{newInstName inputNet outputNet}`. For an inverter pair,
  the return list can contain six fields for the two inserted inverters and
  their input/output nets.

Examples:

```tcl
# Insert a buffer on a net at an automatically selected location.
ecoAddRepeater -net top/u1/net_a -cell BUFX4

# Insert a buffer at an explicit location.
ecoAddRepeater -net top/u1/net_a -cell BUFX4 -loc {123.0 450.0}

# Insert a buffer near the sink on a one-sink net.
ecoAddRepeater -net top/u1/net_a -cell BUFX4 -relativeDistToSink 0.1

# Insert a buffer near the driver on a one-sink net.
ecoAddRepeater -net top/u1/net_a -cell BUFX4 -relativeDistToSink 0.9

# Insert a buffer only for selected sinks on the same net.
ecoAddRepeater -term {U1/A U2/B U3/C} -cell BUFX4

# Capture the returned instance/net names.
set r [ecoAddRepeater -net top/u1/net_a -cell BUFX4 -loc {123.0 450.0}]
set newInstName [lindex $r 0]
set inputNetName [lindex $r 1]
set outputNetName [lindex $r 2]
```

Single-inverter insertion:

```tcl
# Default LEQ behavior inserts inverter pairs.
# Disable LEQ check when one single inverter is intended.
setEcoMode -LEQCheck false

ecoAddRepeater \
  -term {U1/A} \
  -cell INVX1 \
  -name ECO_INV_0 \
  -newNetName ECO_INV_NET_0 \
  -noPlace
```

Inverter-pair insertion:

```tcl
setEcoMode -LEQCheck true

ecoAddRepeater \
  -net top/u1/net_a \
  -cell INVX4 \
  -loc {123.0 450.0 145.0 480.0} \
  -name {{ECO_INV_0 ECO_INV_1}} \
  -newNetName {{ECO_N_0 ECO_N_1}}
```

## 3. `setEcoMode`

Purpose: control behavior of interactive ECO commands such as
`ecoAddRepeater` and `ecoDeleteRepeater`.

Syntax subset:

```tcl
setEcoMode \
  [-help] \
  [-reset] \
  [-addPortAsNeeded true|false] \
  [-batchMode true|false] \
  [-honorDontTouch true|false] \
  [-honorDontUse true|false] \
  [-honorFixedNetWire true|false] \
  [-honorFixedStatus true|false] \
  [-honorPowerIntent true|false] \
  [-inheritNetAttr true|false] \
  [-LEQCheck true|false] \
  [-modifyOnlyLayers <bottom_layer>:<top_layer>] \
  [-prefixName <prefix>] \
  [-preserveModuleFunction true|false] \
  [-refinePlace true|false] \
  [-spreadInverter true|false] \
  [-updateTiming true|false] \
  [-delayCalcEffort low|medium|high]
```

Relevant arguments:

| Argument | Description |
|---|---|
| `-LEQCheck true|false` | Controls logical-equivalence checking. With `true`, inverter ECO insertion/deletion uses inverter pairs. With `false`, single-inverter add/delete is allowed. Default is `true`. |
| `-batchMode true|false` | Batch many ECO operations. Must be exited explicitly with `setEcoMode -batchMode false`. |
| `-honorDontTouch true|false` | Honor `dont_touch` nets/instances. Default is `true`. |
| `-honorDontUse true|false` | Honor `dontUse` cells. Default is `true`. |
| `-honorFixedNetWire true|false` | Protect fixed/cover net wires. Default is `true`. |
| `-honorFixedStatus true|false` | Protect fixed instances. Default is `true`. |
| `-honorPowerIntent true|false` | Enforce MSV/power-intent checks. Default is `true`. |
| `-refinePlace true|false` | Legalize placement after ECO add/change. Default is `true`. |
| `-updateTiming true|false` | Control timing update after ECO commands. Default is `true`. |
| `-prefixName <prefix>` | Prefix for ECO-inserted cells. |
| `-reset` | Reset ECO mode settings. If used, it must be the first argument. |

Examples:

```tcl
# Allow a single-inverter insertion.
setEcoMode -LEQCheck false
ecoAddRepeater -term {U1/A} -cell INVX1 -name ECO_INV_0 -noPlace

# Batch many ECO changes and update/legalize later.
setEcoMode -batchMode true -updateTiming false -refinePlace false
ecoAddRepeater -net net_a -cell BUFX4 -noPlace
ecoDeleteRepeater -inst U_BUF1 -logicalChangeOnly
setEcoMode -batchMode false

# Restore defaults.
setEcoMode -reset
```

## 4. `ecoDeleteRepeater`

Purpose: delete a buffer or back-to-back inverter pair and merge wires after
ECO.

Syntax:

```tcl
ecoDeleteRepeater \
  [-help] \
  [-logicalChangeOnly] \
  {-inst {list_of_instances} | -invPair {{inv1 inv2} {inv3 inv4} ...}}
```

Arguments:

| Argument | Description |
|---|---|
| `-help` | Print command usage. |
| `-inst {inst1 inst2 ...}` | Buffer or inverter instances to delete. If an inverter is specified and `setEcoMode -LEQCheck true`, Innovus finds the paired inverter and deletes the tied back-to-back pair. |
| `-invPair {{inv1 inv2} ...}` | Explicit inverter pairs to delete/evaluate. |
| `-logicalChangeOnly` | Perform logical-only deletion. |

Manual-confirmed notes:

- `ecoDeleteRepeater` does not modify `dont_touch` nets if
  `setEcoMode -honorDontTouch true`.
- It cannot be used in post-mask ECO; use `loadECO <ecofile> -postMask` for
  post-mask deletion.

Examples:

```tcl
# Delete one buffer.
ecoDeleteRepeater -inst U_BUF1

# Delete multiple repeaters.
ecoDeleteRepeater -inst {U_BUF1 U_BUF2}

# Delete a back-to-back inverter pair containing U_INV1.
ecoDeleteRepeater -inst U_INV1

# Delete explicit inverter pairs.
ecoDeleteRepeater -invPair {{U_INV_A U_INV_B} {U_INV_C U_INV_D}}

# Logical-only deletion.
ecoDeleteRepeater -inst U_BUF1 -logicalChangeOnly
```

## 5. `addRepeaterByRule`

Purpose: insert buffers/inverters according to a rule file. The rules can
constrain max net length, max radius length, max capacitance, max fanout, and
related metrics.

Syntax:

```tcl
addRepeaterByRule \
  [-help] \
  [-allowMixedSignal] \
  [-copyNetAttribute] \
  [-excNet <excludeNetFile>] \
  [-netMapping <fileName>] \
  [-nets {list_of_nets}] \
  [-outDir <directoryName>] \
  [-preRoute | -postRoute | -alongRoute] \
  [-reportIgnoredNets <ignoredNetFile>] \
  [-rule <fileName>] \
  [-selNet <selNetFile>] \
  [-selected] \
  [-template]
```

Arguments:

| Argument | Description |
|---|---|
| `-rule <file>` | Rule file listing legal repeaters and constraints. Only buffers/inverters in the rule file are inserted. |
| `-nets {net1 net2 ...}` | Process listed nets. Mutually exclusive with `-selNet` and `-selected`. |
| `-selNet <file>` | Process nets listed in a file. Mutually exclusive with `-nets` and `-selected`. |
| `-selected` | Process nets selected in GUI or by `selectNet`. Mutually exclusive with `-nets` and `-selNet`. |
| `-excNet <file>` | Exclude nets listed in a file. |
| `-preRoute` | Insert repeaters before detailed route; database should be global-routed with pre-route RC extraction. |
| `-postRoute` | Insert repeaters after detailed route with detailed RC extraction; routing changes are minimized. |
| `-alongRoute` | Insert repeaters along the route; database should be global-routed with pre-route RC extraction. |
| `-netMapping <file>` | Write original-to-new net mapping. |
| `-outDir <dir>` | Directory for detailed failure reports. Default report root is `timingReports`. |
| `-copyNetAttribute` | Copy original net attributes to inserted nets. |
| `-allowMixedSignal` | Allow buffering on mixed-signal nets. |
| `-reportIgnoredNets <file>` | Report nets where no buffers were inserted and why. |
| `-template` | Write a template rule file. Other parameters are ignored. |

Manual-confirmed caution:

- `addRepeaterByRule` does not legalize newly added buffers. Run placement
  legalization/refinement and ECO routing as appropriate.

Minimal rule file example:

```tcl
# repeater.rule
SetBufferMaxNetLength BUFX4 300.0
SetInverterMaxNetLength INVX1 150.0
SetDefaultMaxNetLength 100.0
SetDefaultMaxFanout 20
```

Examples:

```tcl
# Generate a template rule file.
addRepeaterByRule -template

# Pre-route rule-based insertion on selected nets.
addRepeaterByRule \
  -rule repeater.rule \
  -preRoute \
  -nets {net_a net_b} \
  -netMapping repeater_net_map.txt \
  -outDir timingReports

# Post-route insertion along detailed route.
addRepeaterByRule \
  -rule repeater.rule \
  -postRoute \
  -selNet selected_nets.txt \
  -reportIgnoredNets ignored_nets.rpt
```

## 6. Naming behavior of modified netlists

This section covers instance/net names created or preserved by the native
buffer insertion/deletion commands. It is based on the Innovus 25.11 manual and
small Innovus experiments on 2026-07-10 using `v25.11-s102_1`.

### 6.1 `ecoAddRepeater` with explicit names

Manual-confirmed behavior:

- `-name <instName>` specifies the base name for the inserted repeater instance.
- `-newNetName <netName>` specifies the base name for the new net created by
  repeater insertion.
- For inverter pairs, specify two names using nested braces:
  `-name {{inv0 inv1}} -newNetName {{net0 net1}}`.
- The command returns the created instance/net names.

Observed single-buffer result:

```tcl
set r [ecoAddRepeater \
  -net net_a \
  -cell BUFX4 \
  -name MY_BUF \
  -newNetName MY_NET \
  -logicalChangeOnly]
```

Return list shape:

```text
MY_BUF net_a MY_NET
```

Netlist connectivity shape:

```text
driver/Y -> net_a -> MY_BUF/A
MY_BUF/Y -> MY_NET -> sinks
```

So, for a single inserted buffer:

| Return field | Meaning |
|---|---|
| `[lindex $r 0]` | New instance name. |
| `[lindex $r 1]` | Input-side net name. This is usually the original net. |
| `[lindex $r 2]` | Output-side net name. This is the inserted/new net. |

Observed inverter-pair result:

```tcl
setEcoMode -LEQCheck true

set r [ecoAddRepeater \
  -net net_a \
  -cell INVX1 \
  -name {{I0 I1}} \
  -newNetName {{N0 N1}} \
  -logicalChangeOnly]
```

Return list shape:

```text
I0 net_a N0 I1 N0 N1
```

Netlist connectivity shape:

```text
driver/Y -> net_a -> I0/A
I0/Y     -> N0    -> I1/A
I1/Y     -> N1    -> sinks
```

So, for an inverter pair:

| Return field | Meaning |
|---|---|
| `[lindex $r 0]` | First inverter instance. |
| `[lindex $r 1]` | First inverter input net, usually the original net. |
| `[lindex $r 2]` | First inverter output net. |
| `[lindex $r 3]` | Second inverter instance. |
| `[lindex $r 4]` | Second inverter input net, same net as field 2. |
| `[lindex $r 5]` | Second inverter output net. |

### 6.2 `ecoAddRepeater` with automatic names

If `-name` and `-newNetName` are omitted, Innovus generates names. In the
experiment, the default ECO prefix produced:

```text
instance: FE_ECOC0_net_a
new net : FE_ECON0_net_a
return  : FE_ECOC0_net_a net_a FE_ECON0_net_a
```

After:

```tcl
setEcoMode -prefixName TESTECO
```

the generated names became:

```text
instance: FE_TESTECOC0_net_a
new net : FE_TESTECON0_net_a
return  : FE_TESTECOC0_net_a net_a FE_TESTECON0_net_a
```

Manual note: `setEcoMode -prefixName <prefix>` adds a prefix to ECO-inserted
cells. The observed generated names use the prefix inside the `FE_<prefix>C...`
and `FE_<prefix>N...` naming pattern. If exact names matter, prefer explicit
`-name` and `-newNetName`, or capture the return list.

### 6.3 `ecoAddRepeater` on selected sinks

When using `-term`, Innovus cuts only the selected sink terminals away from the
common source net.

Observed single-inverter example:

```tcl
setEcoMode -LEQCheck false

set r [ecoAddRepeater \
  -term {U_SINK/A} \
  -cell INVX1 \
  -name S_INV \
  -newNetName S_NET \
  -logicalChangeOnly]
```

Observed connectivity shape:

```text
driver/Y -> original_net -> S_INV/A and unselected sinks
S_INV/Y  -> S_NET        -> selected sink
```

### 6.4 `ecoDeleteRepeater` net merge naming

Manual-confirmed behavior: `ecoDeleteRepeater` deletes a buffer or
back-to-back inverter pair and merges wires after ECO. The manual does not
provide a user option for choosing the merged net name.

Observed single-buffer deletion:

Before:

```text
driver/Y -> n0 -> U_BUF/A
U_BUF/Y  -> n1 -> sink/A
```

Command:

```tcl
ecoDeleteRepeater -inst U_BUF -logicalChangeOnly
```

After:

```text
driver/Y -> n0 -> sink/A
```

Observed result: the driver/input-side net `n0` survived, and the
buffer-output-side net `n1` was removed.

### 6.5 `deleteBufferTree` net merge naming

Manual-confirmed behavior: `deleteBufferTree` removes eligible buffers and
inverter pairs. It does not provide `-name` or `-newNetName` controls.

Observed single-buffer deletion with non-buffer driver/sink:

Before:

```text
driver/Y -> n0 -> U_BUF/A
U_BUF/Y  -> n1 -> sink/A
```

Commands tested:

```tcl
deleteBufferTree -net {n0} -verbose
deleteBufferTree -net {n1} -verbose
```

After, in both tests:

```text
driver/Y -> n0 -> sink/A
```

Observed result: the driver/input-side net `n0` survived, and the
buffer-output-side net `n1` was removed. If an exact survivor name is critical,
verify on the target design because the manual describes wire merging but does
not explicitly guarantee a net-name survivor rule.

### 6.6 `addRepeaterByRule` naming

Manual/user-guide confirmed behavior:

- `addRepeaterByRule -netMapping <file>` writes original-to-new net mappings.
- The manual example maps an original net to generated names like
  `FE_new_net1_<origNet>` and `FE_new_net2_<origNet>`.
- The Innovus user guide default naming convention lists:
  - `FE_ARRC`: instance added by `add_repeater_by_rule`
  - `FE_ARRN`: net added by `add_repeater_by_rule`

Use `-netMapping` whenever names must be consumed by downstream scripts:

```tcl
addRepeaterByRule \
  -rule repeater.rule \
  -preRoute \
  -nets {net_a net_b} \
  -netMapping repeater_net_map.txt
```

## 7. Small key workflows

### 7.1 Run `deleteBufferTree` only on selected nets

```tcl
deleteBufferTree \
  -net {net_a net_b net_c} \
  -preserveRoute \
  -verbose
```

### 7.2 Insert one ECO buffer and record names

```tcl
set result [ecoAddRepeater \
  -net net_a \
  -cell BUFX4 \
  -loc {123.0 450.0}]

puts "new instance = [lindex $result 0]"
puts "input net    = [lindex $result 1]"
puts "output net   = [lindex $result 2]"
```

### 7.3 Insert one single ECO inverter

```tcl
setEcoMode -LEQCheck false

set result [ecoAddRepeater \
  -term {U_SINK/A} \
  -cell INVX1 \
  -name ECO_INV_0 \
  -newNetName ECO_N_0 \
  -noPlace]

puts "single inverter ECO result = $result"
```

### 7.4 Delete one ECO buffer

```tcl
ecoDeleteRepeater -inst U_BUF1
```
