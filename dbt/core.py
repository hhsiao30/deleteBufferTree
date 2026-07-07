from dataclasses import dataclass, field
from collections import defaultdict, deque
from .def_parser import Component, Net

@dataclass
class DbtStats:
    removed: set = field(default_factory=set)
    inserted: list = field(default_factory=list)
    skipped_single_inv: int = 0
    skipped_clock: int = 0
    skipped_island: int = 0
    trees: int = 0
    degenerate: int = 0
    pin_net_rewrites: int = 0

def compute_clock_cone(d, cfg, clock_ports):
    """Forward closure from SDC clock ports: nets carrying (ideal) clock.
    Propagates through any non-sequential cell (clock gates, muxes, buffers);
    stops at clock pins of sequential cells (flops/memories)."""
    seq = set()
    comp_outs = defaultdict(list)   # comp -> [net names it drives]
    for n in d.nets.values():
        for comp, pin in n.terms:
            if comp == "PIN" or comp not in d.components:
                continue
            cell = d.components[comp].cell
            if cfg.is_clock_pin(cell, pin):
                seq.add(comp)
            if pin in cfg.out_pins_of(cell):
                comp_outs[comp].append(n.name)
    cone = set()
    q = deque()
    for p in clock_ports:
        n = d.pin_nets.get(p)
        if n:
            cone.add(n); q.append(n)
    while q:
        net = q.popleft()
        for comp, pin in d.nets[net].terms:
            if comp == "PIN" or comp in seq or comp not in d.components:
                continue
            cell = d.components[comp].cell
            if cfg.is_clock_pin(cell, pin):
                continue
            if pin in cfg.out_pins_of(cell):
                continue   # this term drives the net; do not walk backwards
            for onet in comp_outs.get(comp, []):
                if onet not in cone:
                    cone.add(onet); q.append(onet)
    return cone

def run_dbt(d, cfg, clock_cone=None) -> DbtStats:
    stats = DbtStats()
    cellof = {n: c.cell for n, c in d.components.items()}
    kind = {}
    for name, cell in cellof.items():
        k = cfg.classify(cell)
        if k:
            kind[name] = k

    def is_bi_in(comp, pin):
        return comp in kind and cfg.is_bi_in_pin(cellof[comp], pin)

    def is_bi_out(comp, pin):
        return comp in kind and cfg.is_bi_out_pin(cellof[comp], pin)

    def is_clock_term(comp, pin):
        if comp == "PIN" or comp not in cellof:
            return False
        return cfg.is_clock_pin(cellof[comp], pin)

    in_net = {}    # BI inst -> its input net
    out_net = {}   # BI inst -> its output net
    for n in d.nets.values():
        for comp, pin in n.terms:
            if comp in kind:
                if cfg.is_bi_in_pin(cellof[comp], pin):
                    in_net[comp] = n.name
                elif cfg.is_bi_out_pin(cellof[comp], pin):
                    out_net[comp] = n.name
    # valid BI = both pins recognized; others are degenerate and act as logic.
    # NOTE: a broader "input net must have a driver" rule (Innovus ignores undriven
    # cones) was tried twice and reverted twice: DEF-view driver existence diverges
    # from Innovus's DB view on testcases whose DEF/netlist are out of sync (ariane's
    # 54 uncreated ports). The narrow island rule below is the safe validated form.
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
    port_net_of = {}   # net name -> port name (for the port-naming rule)
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
        member_set = {m for m, _ in members}
        tree_has_sink = False
        for inst, _p in members:
            onet = d.nets.get(out_net[inst])
            if onet is None:
                continue
            for c, p in onet.terms:
                if c == inst and is_bi_out(c, p):
                    continue
                if c in member_set and is_bi_in(c, p):
                    continue
                tree_has_sink = True
                break
            if tree_has_sink:
                break
        # complete island (probe-verified): the root net carries NOTHING except the
        # members' own input pins (no driver term of any kind, no other loads) and
        # the tree has zero sinks -> Innovus never touches it. Direction-agnostic:
        # any non-member term on the root disqualifies (macro-driven nets included).
        root_all_member_inputs = all(
            c in member_set and is_bi_in(c, p) for c, p in d.nets[R].terms)
        if not tree_has_sink and root_all_member_inputs:
            stats.skipped_island += 1
            continue
        if len(members) == 1 and kind[members[0][0]] == "INV":
            if tree_has_sink:
                stats.skipped_single_inv += 1
                continue
            # driven single INV with zero sinks: dead cell, Innovus deletes it
        # tree-level clock exemption: any clock-pin sink anywhere in the tree
        # => whole tree untouched (verified: NVDLA 17/17 CLK trees fully kept,
        # including 5 mixed clock+data trees)
        if clock_cone and (R in clock_cone
                           or any(out_net[i] in clock_cone for i, _p in members)):
            stats.skipped_clock += 1
            continue
        hit = any(is_clock_term(c, p) for c, p in d.nets[R].terms)
        for inst, _p in members:
            if hit:
                break
            onet = d.nets.get(out_net[inst])
            if onet is None:
                continue
            for comp, pin in onet.terms:
                if comp not in member_set and is_clock_term(comp, pin):
                    hit = True
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
                if comp == inst and is_bi_out(comp, pin):
                    continue
                if comp in member_set and is_bi_in(comp, pin):
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
                      if not (t[0] in member_set and is_bi_in(t[0], t[1]))]
        root.terms += even_sinks
        if even_port_nets:                       # port net name wins the merge
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
            cellof[iname] = cfg.new_cell
            d.nets[nname] = Net(nname,
                                [(iname, cfg.new_cell_out_pin)] + odd_sinks, "")
            for other in odd_port_nets[1:]:
                if other != nname:
                    d.mid = d.mid.replace(f"+ NET {other}", f"+ NET {nname}")
                    stats.pin_net_rewrites += 1
            d.nets[R].terms.append((iname, cfg.new_cell_in_pin))
            stats.inserted.append(iname)
    return stats
