"""Liberty-driven node config: classify buffers/inverters from cell function,
pin directions and clock pins straight from .lib files. No name patterns,
no per-node hardcoding, no NDA side files."""
import gzip, re


def _read(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="ignore").read()
    return open(path, errors="ignore").read()


_CELL = re.compile(r'^\s*cell\s*\(\s*"?([\w\[\]]+)"?\s*\)\s*\{', re.M)
_PIN = re.compile(r'^(\s*)pin\s*\(\s*"?([\w\[\]]+)"?\s*\)\s*\{', re.M)


def _cell_bodies(txt):
    ms = list(_CELL.finditer(txt))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(txt)
        yield m.group(1), txt[m.end():end]


def _norm_expr(e):
    return e.replace(" ", "").replace("(", "").replace(")", "")


class LibertyConfig:
    """Same interface core.py consumes; built from .lib files."""

    def __init__(self, new_inst_prefix="DBT_", new_net_prefix="DBT_N_"):
        self.bi = {}           # cell -> (kind, in_pin, out_pin)
        self.clock = {}        # cell -> set(clock pin names)
        self.outputs = {}      # cell -> set(output pin names)
        self.area = {}         # cell -> float
        self.new_cell = None
        self.new_cell_in_pin = None
        self.new_cell_out_pin = None
        self.new_inst_prefix = new_inst_prefix
        self.new_net_prefix = new_net_prefix

    # ---- construction ----
    def load(self, path):
        txt = _read(path)
        for name, body in _cell_bodies(txt):
            self._load_cell(name, body)
        return self

    def _load_cell(self, name, body):
        is_seq = re.search(r'^\s*(ff|latch)\s*(\(|_bank)', body, re.M) is not None
        ins, outs, funcs, clks = [], [], {}, set()
        for pm in _PIN.finditer(body):
            pstart = pm.end()
            nxt = _PIN.search(body, pstart)
            pbody = body[pstart:nxt.start() if nxt else len(body)]
            pname = pm.group(2)
            d = re.search(r'direction\s*:\s*"?(\w+)', pbody)
            if not d:
                continue
            if re.search(r'^\s*clock\s*:\s*"?true', pbody, re.M):
                clks.add(pname)
            if d.group(1) == "input":
                ins.append(pname)
            elif d.group(1) == "output":
                outs.append(pname)
                f = re.search(r'^\s*function\s*:\s*"([^"]+)"', pbody, re.M)
                if f:
                    funcs[pname] = _norm_expr(f.group(1))
        a = re.search(r'^\s*area\s*:\s*([\d.]+)', body, re.M)
        if a:
            self.area[name] = float(a.group(1))
        if outs:
            self.outputs[name] = set(outs)
        if clks:
            self.clock[name] = clks
        if is_seq or len(ins) != 1 or len(outs) != 1:
            return
        i, o = ins[0], outs[0]
        f = funcs.get(o)
        if f == i:
            self.bi[name] = ("BUF", i, o)
        elif f in ("!" + i, i + "'"):
            self.bi[name] = ("INV", i, o)

    def finalize(self, new_cell=None):
        if new_cell is None:
            invs = [(self.area.get(c, 1e9), c)
                    for c, (k, _i, _o) in self.bi.items() if k == "INV"]
            if not invs:
                raise ValueError("no inverter found in the loaded liberty files")
            new_cell = min(invs)[1]
            print(f"WARNING: --new-cell not given; auto-picked min-area inverter "
                  f"'{new_cell}' (pass --new-cell to match a specific tool's choice)")
        if new_cell not in self.bi or self.bi[new_cell][0] != "INV":
            raise ValueError(f"--new-cell '{new_cell}' is not an inverter in the libs")
        self.new_cell = new_cell
        _k, self.new_cell_in_pin, self.new_cell_out_pin = self.bi[new_cell]
        return self

    # ---- interface used by core/comparator ----
    def classify(self, cell):
        e = self.bi.get(cell)
        return e[0] if e else None

    def is_bi_in_pin(self, cell, pin):
        e = self.bi.get(cell)
        return bool(e) and pin == e[1]

    def is_bi_out_pin(self, cell, pin):
        e = self.bi.get(cell)
        return bool(e) and pin == e[2]

    def is_clock_pin(self, cell, pin):
        return pin in self.clock.get(cell, ())

    def has_clock_pin(self, cell):
        return cell in self.clock

    def out_pins_of(self, cell):
        return self.outputs.get(cell, ())


def load_liberty_config(paths, new_cell=None):
    cfg = LibertyConfig()
    for p in paths:
        cfg.load(p)
    return cfg.finalize(new_cell)


# ---- standalone pin-dump CLI:  python3 -m dbt.liberty --libs <files/globs> --out pins.csv
def _dump_pins(paths, out_csv):
    import csv, sys
    rows = []
    for path in paths:
        txt = _read(path)
        libname = path.split("/")[-1]
        for cname, body in _cell_bodies(txt):
            is_seq = re.search(r'^\s*(ff|latch)\s*(\(|_bank)', body, re.M) is not None
            a = re.search(r'^\s*area\s*:\s*([\d.]+)', body, re.M)
            for pm in _PIN.finditer(body):
                nxt = _PIN.search(body, pm.end())
                pbody = body[pm.end():nxt.start() if nxt else len(body)]
                d = re.search(r'direction\s*:\s*"?(\w+)', pbody)
                f = re.search(r'^\s*function\s*:\s*"([^"]+)"', pbody, re.M)
                clk = bool(re.search(r'^\s*clock\s*:\s*"?true', pbody, re.M))
                rows.append([libname, cname, pm.group(2),
                             d.group(1) if d else "", f.group(1) if f else "",
                             int(clk), int(is_seq), a.group(1) if a else ""])
    w = csv.writer(open(out_csv, "w", newline=""))
    w.writerow(["lib", "cell", "pin", "direction", "function",
                "is_clock", "cell_is_seq", "cell_area"])
    w.writerows(rows)
    print(f"{len(rows)} pins from {len(paths)} lib files -> {out_csv}")

if __name__ == "__main__":
    import argparse, glob as _glob
    ap = argparse.ArgumentParser(description="Liberty pin dumper / classifier")
    ap.add_argument("--libs", nargs="+", required=True,
                    help="liberty files or globs (.lib / .lib.gz)")
    ap.add_argument("--out", default="pins.csv")
    a = ap.parse_args()
    files = []
    for g in a.libs:
        files += sorted(_glob.glob(g)) or [g]
    _dump_pins(files, a.out)
