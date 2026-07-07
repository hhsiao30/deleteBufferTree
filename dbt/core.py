from dataclasses import dataclass, field
from collections import defaultdict, deque
from .def_parser import Component, Net

@dataclass
class DbtStats:
    removed: set = field(default_factory=set)
    inserted: list = field(default_factory=list)
    skipped_single_inv: int = 0
    skipped_clock: int = 0
    trees: int = 0
    degenerate: int = 0
    pin_net_rewrites: int = 0

def run_dbt(d, cfg) -> DbtStats:
    stats = DbtStats()
    kind = {}
    for name, c in d.components.items():
        k = cfg.classify(c.cell)
        if k:
            kind[name] = k

    in_net = {}    # BI inst -> its input net
    out_net = {}   # BI inst -> its output net
    for n in d.nets.values():
        for comp, pin in n.terms:
            if comp in kind:
                if pin in cfg.in_pins:
                    in_net[comp] = n.name
                elif pin in cfg.out_pins:
                    out_net[comp] = n.name
    # valid BI = both pins recognized; others are degenerate and act as logic
    invalid = {c for c in kind if c not in in_net or c not in out_net}
    stats.degenerate = len(invalid)
    for c in invalid:
        kind.pop(c); in_net.pop(c, None); out_net.pop(c, None)
    bi_loads = defaultdict(list)   # net -> [BI inst]
    bi_driver = {}                 # net -> BI inst
    for c in kind:
        bi_loads[in_net[c]].append(c)
        bi_driver[out_net[c]] = c

    counter = 0
    port_net_of = {}   # net name -> port name (for the C1 naming rule)
    for p, n in d.pin_nets.items():
        port_net_of[n] = p
    for R in list(d.nets):
        if not bi_loads.get(R) or bi_driver.get(R):
            continue   # not a root: no BI loads, or driven by a BI cell (internal net)
        # BFS collect members
        members = []          # (inst, parity)  parity counts INV on path incl. self
        q = deque((b, 0) for b in bi_loads[R])
        seen = set()
        while q:
            inst, par_above = q.popleft()
            if inst in seen or inst not in d.components:
                continue
            seen.add(inst)
            par = par_above + (1 if kind[inst] == "INV" else 0)
            members.append((inst, par))
            for child in bi_loads.get(out_net[inst], []):
                q.append((child, par))
        if not members:
            continue
        stats.trees += 1
        if len(members) == 1 and kind[members[0][0]] == "INV":
            stats.skipped_single_inv += 1
            continue
        member_set = {m for m, _ in members}
        # tree-level clock exemption: any clock-pin sink anywhere in the tree
        # => whole tree untouched (verified: NVDLA 17/17 CLK trees fully kept,
        # including 5 mixed clock+data trees)
        clock_pins = cfg.clock_pins or set()
        if clock_pins:
            hit = False
            for inst, _p in members:
                onet = d.nets.get(out_net[inst])
                if onet is None:
                    continue
                for comp, pin in onet.terms:
                    if comp not in member_set and pin in clock_pins:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                stats.skipped_clock += 1
                continue
        even_sinks, odd_sinks = [], []
        even_port_nets, odd_port_nets = [], []
        for inst, par in members:
            onet = d.nets.get(out_net[inst])
            if onet is None:
                continue
            is_port_net = onet.name in port_net_of
            for comp, pin in onet.terms:
                if comp == inst and pin in cfg.out_pins:
                    continue
                if comp in member_set and pin in cfg.in_pins:
                    continue
                if par % 2:
                    odd_sinks.append((comp, pin))
                    if is_port_net and comp == "PIN":
                        odd_port_nets.append(onet.name)
                else:
                    even_sinks.append((comp, pin))
                    if is_port_net and comp == "PIN":
                        even_port_nets.append(onet.name)
        for inst, _ in members:
            stats.removed.add(inst)
            del d.components[inst]
            d.nets.pop(out_net[inst], None)
        root = d.nets[R]
        root.terms = [t for t in root.terms
                      if not (t[0] in member_set and t[1] in cfg.in_pins)]
        root.terms += even_sinks
        if even_port_nets:                       # C1: port net name wins the merge
            keep = even_port_nets[0]
            del d.nets[R]
            root.name = keep
            d.nets[keep] = root
            for other in even_port_nets[1:]:     # rare multi-port merge: fix PINS refs
                if other != keep:
                    d.mid = d.mid.replace(f"+ NET {other}", f"+ NET {keep}")
                    stats.pin_net_rewrites += 1
            R = keep
        if odd_sinks:
            iname = f"{cfg.new_inst_prefix}{counter}"
            nname = odd_port_nets[0] if odd_port_nets else f"{cfg.new_net_prefix}{counter}"
            counter += 1
            d.components[iname] = Component(iname, cfg.new_cell, "+ SOURCE TIMING")
            d.nets[nname] = Net(nname,
                                [(iname, cfg.new_cell_out_pin)] + odd_sinks, "")
            for other in odd_port_nets[1:]:
                if other != nname:
                    d.mid = d.mid.replace(f"+ NET {other}", f"+ NET {nname}")
                    stats.pin_net_rewrites += 1
            d.nets[R].terms.append((iname, cfg.new_cell_in_pin))
            stats.inserted.append(iname)
    return stats
