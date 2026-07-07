import argparse, sys, os
from dataclasses import dataclass, field
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dbt.def_parser import parse_def
from dbt.cells import get_config
from collections import Counter

@dataclass
class Report:
    removed_only_ours: set = field(default_factory=set)
    removed_only_gold: set = field(default_factory=set)
    sig_only_ours: list = field(default_factory=list)
    sig_only_gold: list = field(default_factory=list)
    sink_mismatches: list = field(default_factory=list)
    integrity_errors: list = field(default_factory=list)
    insert_count_ours: int = 0
    insert_count_gold: int = 0
    perfect: bool = False

def _new_inst_index(pre, x, cfg):
    """new_inst -> (root_net, out_net)."""
    news = {n for n in x.components if n not in pre.components}
    in_of, out_of = {}, {}
    for net in x.nets.values():
        for comp, pin in net.terms:
            if comp in news:
                cell = x.components[comp].cell
                if cfg.is_bi_in_pin(cell, pin) or pin == cfg.new_cell_in_pin:
                    in_of[comp] = net.name
                elif cfg.is_bi_out_pin(cell, pin) or pin == cfg.new_cell_out_pin:
                    out_of[comp] = net.name
    return news, in_of, out_of

def _sink_map(pre, x, cfg):
    """(comp,pin) -> (source_root, parity) for every surviving/PIN sink term.
    Hardened per review M2: duplicate (comp,pin) on >1 net is an integrity error;
    every new inst must be exactly cfg.new_cell."""
    news, in_of, out_of = _new_inst_index(pre, x, cfg)
    owner = {onet: i for i, onet in out_of.items()}
    m, errors = {}, []
    for i in news:
        if x.components[i].cell != cfg.new_cell:
            errors.append(("BAD_NEW_CELL", i, x.components[i].cell))
    for net in x.nets.values():
        for comp, pin in net.terms:
            if comp in news:
                continue
            if net.name in owner:
                src = (in_of.get(owner[net.name], "?"), 1)
            else:
                src = (net.name, 0)
            if (comp, pin) in m and m[(comp, pin)] != src:
                errors.append(("DUP_TERM", (comp, pin), m[(comp, pin)], src))
            m[(comp, pin)] = src
    # PINS integrity: every port's '+ NET' must reference an existing net
    # that actually contains the ( PIN port ) term
    for port, netname in x.pin_nets.items():
        net = x.nets.get(netname)
        if net is None or ("PIN", port) not in net.terms:
            errors.append(("DANGLING_PIN", port, netname))
    return m, news, in_of, out_of, errors

def _sig(x, news, in_of, out_of):
    """new-inst signature: (root net, frozenset of sinks on its output net)."""
    sigs = Counter()
    for i in news:
        onet = x.nets.get(out_of.get(i, ""), None)
        sinks = frozenset(t for t in (onet.terms if onet else []) if t[0] != i)
        sigs[(in_of.get(i, "?"), sinks)] += 1
    return sigs

def compare(pre_p, ours_p, gold_p, cfg) -> Report:
    pre, ours, gold = parse_def(pre_p), parse_def(ours_p), parse_def(gold_p)
    r = Report()
    rem_o = set(pre.components) - set(ours.components)
    rem_g = set(pre.components) - set(gold.components)
    r.removed_only_ours = rem_o - rem_g
    r.removed_only_gold = rem_g - rem_o
    mo, news_o, in_o, out_o, err_o = _sink_map(pre, ours, cfg)
    mg, news_g, in_g, out_g, err_g = _sink_map(pre, gold, cfg)
    r.integrity_errors = [("ours",) + e for e in err_o] + [("gold",) + e for e in err_g]
    r.insert_count_ours, r.insert_count_gold = len(news_o), len(news_g)
    sig_o = _sig(ours, news_o, in_o, out_o)
    sig_g = _sig(gold, news_g, in_g, out_g)
    r.sig_only_ours = sorted((sig_o - sig_g).elements())
    r.sig_only_gold = sorted((sig_g - sig_o).elements())
    for term in set(mo) | set(mg):
        a, b = mo.get(term), mg.get(term)
        if a != b:
            r.sink_mismatches.append((term, a, b))
    # surviving comps must keep their cell (resize would be a rule violation)
    for name in set(pre.components) & set(ours.components) & set(gold.components):
        co, cg = ours.components[name].cell, gold.components[name].cell
        if co != cg:
            r.integrity_errors.append(("CELL_DIFF", name, co, cg))
    r.perfect = not (r.removed_only_ours or r.removed_only_gold
                     or r.sig_only_ours or r.sig_only_gold
                     or r.sink_mismatches or r.integrity_errors)
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", required=True)
    ap.add_argument("--ours", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--node")
    ap.add_argument("--lib", nargs="+")
    ap.add_argument("--new-cell")
    ap.add_argument("--dump", help="write full mismatch lists to this file")
    a = ap.parse_args()
    if a.lib:
        import glob as _glob
        from dbt.liberty import load_liberty_config
        files = []
        for g in a.lib:
            files += sorted(_glob.glob(g)) or [g]
        cfg = load_liberty_config(files, a.new_cell)
    else:
        cfg = get_config(a.node)
    r = compare(a.pre, a.ours, a.golden, cfg)
    print(f"removed: ours-only={len(r.removed_only_ours)} gold-only={len(r.removed_only_gold)}")
    print(f"inserted: ours={r.insert_count_ours} gold={r.insert_count_gold}")
    print(f"insert-sig diff: ours-only={len(r.sig_only_ours)} gold-only={len(r.sig_only_gold)}")
    print(f"sink mismatches: {len(r.sink_mismatches)}")
    print(f"integrity errors: {len(r.integrity_errors)}")
    for e in r.integrity_errors[:10]:
        print(f"  {e}")
    for t, x, y in r.sink_mismatches[:10]:
        print(f"  {t}: ours={x} gold={y}")
    if a.dump:
        with open(a.dump, "w") as f:
            for s in sorted(r.removed_only_ours): f.write(f"REMOVED_ONLY_OURS {s}\n")
            for s in sorted(r.removed_only_gold): f.write(f"REMOVED_ONLY_GOLD {s}\n")
            for t, x, y in r.sink_mismatches: f.write(f"SINK {t} ours={x} gold={y}\n")
            for e in r.integrity_errors: f.write(f"INTEGRITY {e}\n")
            for s in r.sig_only_ours: f.write(f"SIG_ONLY_OURS {s}\n")
            for s in r.sig_only_gold: f.write(f"SIG_ONLY_GOLD {s}\n")
    print("VERDICT:", "PERFECT" if r.perfect else "MISMATCH")
    sys.exit(0 if r.perfect else 1)

if __name__ == "__main__":
    main()
