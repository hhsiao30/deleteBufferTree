#!/bin/bash
# gen_golden.sh <node> <design> — generate an Innovus deleteBufferTree golden pair.
# Recipe identical to the ariane runs validated 2026-07-06 (minus saveDesign).
# Output: /cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_<node>_batch/<design>/
set -e
NODE=$1; D=$2
CEDAR=/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_${NODE}_batch/$D
mkdir -p $CEDAR
TCL=$CEDAR/run_dbt_golden.tcl

if [ "$NODE" = "asap7" ]; then
  P=/nethome/hhsiao30/asap7/ICCAD25_testcases/$D
  NETLIST=$P/${D}_fixed.v; [ -f "$NETLIST" ] || NETLIST=$P/$D.v
  cat > $TCL <<EOF
setMultiCpuUsage -localCpu 8
set TECH_PATH /nethome/hhsiao30/asap7/ASAP7
set LIB_FILES [glob \$TECH_PATH/LIB/*.lib]
set LEF_FILES ""
append LEF_FILES "\$TECH_PATH/techlef/asap7_tech_1x_201209.lef "
foreach lef [glob \$TECH_PATH/LEF/*.lef] { append LEF_FILES "\$lef " }
create_library_set   -name fast -timing \$LIB_FILES
create_constraint_mode -name fast -sdc_files $P/$D.sdc
create_rc_corner     -name fast -preRoute_res 1 -preRoute_cap 1 -T 25 -qx_tech_file \$TECH_PATH/qrc/qrcTechFile_typ03_unscaledV02
create_delay_corner  -name fast -library_set fast -rc_corner fast
create_analysis_view -name fast -constraint_mode fast -delay_corner fast
set init_verilog $NETLIST
set init_top_cell $D
set init_pwr_net {VDD}
set init_gnd_net {VSS}
set init_lef_file "\$LEF_FILES"
init_design -setup {fast} -hold {fast}
set_analysis_view -setup {fast} -hold {fast}
defIn $P/$D.def
globalNetConnect VDD -type pgpin -pin VDD -inst * -verbose
globalNetConnect VSS -type pgpin -pin VSS -inst * -verbose
globalNetConnect VDD -type tiehi -inst * -verbose
globalNetConnect VSS -type tielo -inst * -verbose
defOut -floorplan -netlist -routing $CEDAR/${D}_pre_deleteBufferTree.def
redirect "$CEDAR/deleteBufferTree.log" { deleteBufferTree -verbose }
defOut -floorplan -netlist -routing -unplaced $CEDAR/${D}_post_deleteBufferTree_withUnplaced.def
puts "DONE golden $D"
exit
EOF
else
  EN=/nethome/hhsiao30/routing-benchmarks/tech/tsmcn7_enablement
  P=/nethome/hhsiao30/routing-benchmarks/tsmcn7/$D/original
  cat > $TCL <<EOF
setMultiCpuUsage -localCpu 8
set EN $EN
set LEF_FILES "\$EN/lef/tech_n7.lef "
foreach lef [glob \$EN/lef/tcbn07*.lef] { append LEF_FILES "\$lef " }
foreach lef [glob -nocomplain \$EN/mem/*/LEF/*.lef] { append LEF_FILES "\$lef " }
set LIB_FILES [glob \$EN/lib/*tt_0p75v_25c_typical.lib.gz]
foreach l [glob -nocomplain \$EN/mem/*/NLDM/*.lib] { lappend LIB_FILES \$l }
create_library_set     -name fast -timing \$LIB_FILES
create_constraint_mode -name fast -sdc_files $P/$D.sdc
create_rc_corner       -name fast -preRoute_res 1 -preRoute_cap 1 -T 25 -qx_tech_file \$EN/qrc/qrcTechFile
create_delay_corner    -name fast -library_set fast -rc_corner fast
create_analysis_view   -name fast -constraint_mode fast -delay_corner fast
set init_verilog  $P/$D.v
set init_top_cell $D
set init_pwr_net {VDD}
set init_gnd_net {VSS}
set init_lef_file "\$LEF_FILES"
init_design -setup {fast} -hold {fast}
set_analysis_view -setup {fast} -hold {fast}
setDesignMode -process 7
defIn $P/$D.def
globalNetConnect VDD -type pgpin -pin VDD  -inst * -verbose
globalNetConnect VDD -type pgpin -pin VDDM -inst * -verbose
globalNetConnect VSS -type pgpin -pin VSS  -inst * -verbose
globalNetConnect VDD -type tiehi -inst * -verbose
globalNetConnect VSS -type tielo -inst * -verbose
defOut -floorplan -netlist -routing $CEDAR/${D}_pre_deleteBufferTree.def
redirect "$CEDAR/deleteBufferTree.log" { deleteBufferTree -verbose }
defOut -floorplan -netlist -routing -unplaced $CEDAR/${D}_post_deleteBufferTree_withUnplaced.def
puts "DONE golden $D"
exit
EOF
fi

export DDI_HOME=/tools/software/cadence/ddi/latest
export CDS_LIC_FILE=5280@ece-winlic.ece.gatech.edu
export CDS_AUTO_64BIT=ALL LANG=C
cd $CEDAR
$DDI_HOME/bin/innovus -64 -nowin -init $TCL -log innovus_golden -overwrite
