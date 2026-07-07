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
    ap.add_argument("--node", required=True, choices=["asap7", "tsmcn7"])
    ap.add_argument("--sdc", help="SDC file: create_clock ports drive clock-cone exemption")
    a = ap.parse_args()
    d = parse_def(a.input)
    cfg = get_config(a.node)
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
