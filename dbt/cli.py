import argparse
from .def_parser import parse_def
from .def_writer import write_def
from .cells import get_config
from .core import run_dbt, compute_clock_cone
import re

def main():
    ap = argparse.ArgumentParser(description="Standalone DEF-in/DEF-out deleteBufferTree")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--node", choices=["asap7", "tsmcn7"],
                    help="builtin preset (legacy)")
    ap.add_argument("--lib", nargs="+",
                    help="liberty files/globs: generic mode, classification from cell functions")
    ap.add_argument("--new-cell", help="compensation inverter cell (generic mode)")
    ap.add_argument("--sdc", help="SDC file: create_clock ports drive clock-cone exemption")
    a = ap.parse_args()
    d = parse_def(a.input)
    if a.lib:
        import glob as _glob
        from .liberty import load_liberty_config
        files = []
        for g in a.lib:
            files += sorted(_glob.glob(g)) or [g]
        cfg = load_liberty_config(files, a.new_cell)
    elif a.node:
        cfg = get_config(a.node)
    else:
        ap.error("need --lib (generic) or --node (preset)")
    cone = None
    if a.sdc:
        ports = re.findall(r"create_clock[^\n]*?get_ports\s*\{?\s*([^\s\}\]]+)", open(a.sdc).read())
        cone = compute_clock_cone(d, cfg, ports)
        print(f"clock cone: {len(ports)} clock ports -> {len(cone)} nets")
    stats = run_dbt(d, cfg, clock_cone=cone)
    write_def(d, a.output)
    print(f"DBT: removed={len(stats.removed)} inserted={len(stats.inserted)} "
          f"trees={stats.trees} skipped_single_inv={stats.skipped_single_inv} skipped_clock={stats.skipped_clock} "
          f"degenerate={stats.degenerate} pin_net_rewrites={stats.pin_net_rewrites}")

if __name__ == "__main__":
    main()
