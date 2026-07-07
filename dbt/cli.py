import argparse
from .def_parser import parse_def
from .def_writer import write_def
from .cells import get_config
from .core import run_dbt

def main():
    ap = argparse.ArgumentParser(description="Standalone DEF-in/DEF-out deleteBufferTree")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--node", required=True, choices=["asap7", "tsmcn7"])
    a = ap.parse_args()
    d = parse_def(a.input)
    stats = run_dbt(d, get_config(a.node))
    write_def(d, a.output)
    print(f"DBT: removed={len(stats.removed)} inserted={len(stats.inserted)} "
          f"trees={stats.trees} skipped_single_inv={stats.skipped_single_inv} "
          f"degenerate={stats.degenerate} pin_net_rewrites={stats.pin_net_rewrites}")

if __name__ == "__main__":
    main()
