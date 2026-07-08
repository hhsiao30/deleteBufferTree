#!/usr/bin/env python3
"""Pre/post deleteBufferTree DEF diff diagnostics.

Usage:
  python3 compare/dbt_diff.py --pre pre.def --post post.def \
      [--node asap7|tsmcn7 | --lib <globs...> [--new-cell CELL]] [--out report.txt]

Reports: component/net deltas, removed cells by BUF/INV class and cell type,
inserted compensation inverters (+merge factors: how many old inverters each
one absorbed), surviving buffer/inverter inventory, and integrity checks.
Classification needs --node or --lib; without it, kind columns show '?'.
"""
import argparse, os, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dbt.def_parser import parse_def


def _cfg(args):
    if args.lib:
        import glob
        from dbt.liberty import load_liberty_config
        files = []
        for g in args.lib:
            files += sorted(glob.glob(g)) or [g]
        return load_liberty_config(files, args.new_cell)
    if args.node:
        from dbt.cells import get_config
        return get_config(args.node)
    return None


def _placement(comp):
    for s in ("FIXED", "COVER", "UNPLACED", "PLACED"):
        if f"+ {s}" in comp.tail:
            return s
    return "UNPLACED"


def diff(pre, post, cfg=None):
    R = {"lines": []}
    say = R["lines"].append
    kind = (lambda c: cfg.classify(c) or "other") if cfg else (lambda c: "?")

    pre_set, post_set = set(pre.components), set(post.components)
    removed = pre_set - post_set
    inserted = post_set - pre_set
    survived = pre_set & post_set

    say("=" * 64)
    say("SUMMARY")
    say(f"  components : pre={len(pre.components):>8,}  post={len(post.components):>8,}"
        f"  delta={len(post.components)-len(pre.components):+,}")
    say(f"  nets       : pre={len(pre.nets):>8,}  post={len(post.nets):>8,}"
        f"  delta={len(post.nets)-len(pre.nets):+,}")
    say(f"  removed={len(removed):,}  inserted={len(inserted):,}"
        f"  net-change={len(inserted)-len(removed):+,}")
    resized = [n for n in survived
               if pre.components[n].cell != post.components[n].cell]
    say(f"  survivors with CELL changed: {len(resized)}"
        + ("  <-- unexpected for deleteBufferTree!" if resized else ""))

    say("")
    say("REMOVED — by class")
    rk = Counter(kind(pre.components[n].cell) for n in removed)
    for k, v in rk.most_common():
        say(f"  {k:6s} {v:>8,}")
    say("REMOVED — top cell types")
    rc = Counter(pre.components[n].cell for n in removed)
    for c, v in rc.most_common(12):
        say(f"  {c:40s} {v:>7,}")

    say("")
    say("INSERTED — by cell / placement")
    ic = Counter((post.components[n].cell, _placement(post.components[n]))
                 for n in inserted)
    for (c, p), v in ic.most_common():
        say(f"  {c:40s} {p:9s} {v:>7,}")

    # merge factor: how many distinct removed INVERTERS feed each new inst's sinks
    # (adversarial-review fix: classify==INV required — buffers must not count;
    #  indexed single pass instead of rescanning all nets per inserted inst)
    if inserted and cfg:
        pre_net_of_term = {}
        pre_net_drv = {}
        for net in pre.nets.values():
            for comp, pin in net.terms:
                pre_net_of_term[(comp, pin)] = net.name
                if (comp in removed
                        and cfg.classify(pre.components[comp].cell) == "INV"
                        and cfg.is_bi_out_pin(pre.components[comp].cell, pin)):
                    pre_net_drv[net.name] = comp
        inst_outs = defaultdict(list)
        for net in post.nets.values():
            for c, p in net.terms:
                if c in inserted and cfg.is_bi_out_pin(post.components[c].cell, p):
                    inst_outs[c].append(net)
        merge = Counter()
        for n in inserted:
            olds = set()
            for net in inst_outs.get(n, []):
                for c, p in net.terms:
                    if c == n:
                        continue
                    pn = pre_net_of_term.get((c, p))
                    if pn and pn in pre_net_drv:
                        olds.add(pre_net_drv[pn])
            merge[len(olds)] += 1
        say("")
        say("INSERTED — merge factor (distinct removed INVERTERS absorbed per new inst)")
        for k in sorted(merge):
            say(f"  absorbed {k:>2d} old INVs : {merge[k]:>7,} new insts")

    say("")
    say("SURVIVING buffer/inverter inventory")
    sk = Counter(kind(pre.components[n].cell) for n in survived)
    for k in ("BUF", "INV"):
        if sk.get(k):
            say(f"  {k:4s} kept: {sk[k]:>8,}")
    if not cfg:
        say("  (pass --node or --lib for BUF/INV classification)")

    say("")
    say("INTEGRITY (post)")
    probs = 0
    post_nets_terms = {(c, p) for net in post.nets.values() for c, p in net.terms}
    for port, netname in post.pin_nets.items():
        net = post.nets.get(netname)
        if net is None or ("PIN", port) not in net.terms:
            say(f"  DANGLING PIN: port '{port}' -> net '{netname}'")
            probs += 1
    ghost = {c for c, _p in post_nets_terms
             if c != "PIN" and c not in post.components}
    if ghost:
        say(f"  NETS reference {len(ghost)} missing components, e.g. {sorted(ghost)[:3]}")
        probs += len(ghost)
    dup = Counter((c, p) for net in post.nets.values()
                  for c, p in net.terms if c != "PIN")
    multi = [t for t, v in dup.items() if v > 1]
    if multi:
        say(f"  {len(multi)} (comp,pin) terms appear more than once across NETS, e.g. {multi[:3]}")
        probs += len(multi)
    if not probs:
        say("  clean (PINS refs valid, no ghost components, no duplicate terms)")
    say("=" * 64)
    return R


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pre", required=True)
    ap.add_argument("--post", required=True)
    ap.add_argument("--node", choices=["asap7", "tsmcn7"])
    ap.add_argument("--lib", nargs="+")
    ap.add_argument("--new-cell")
    ap.add_argument("--out", help="also write the report to this file")
    a = ap.parse_args()
    cfg = _cfg(a)
    rep = diff(parse_def(a.pre), parse_def(a.post), cfg)
    text = "\n".join(rep["lines"])
    print(text)
    if a.out:
        open(a.out, "w").write(text + "\n")


if __name__ == "__main__":
    main()
