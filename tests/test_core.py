from dbt.def_parser import parse_def
from dbt.cells import get_config
from dbt.core import run_dbt

def load():
    d = parse_def("tests/fixtures/mini.def")
    return d, get_config("asap7")

def test_mixed_tree_rebuild():
    d, cfg = load()
    run_dbt(d, cfg)
    # BUF1/INV1 deleted; AOI1,AOI2 direct on netA; OAI1 behind one new inverter
    assert "U_BUF1" not in d.components and "U_INV1" not in d.components
    t = d.nets["netA"].terms
    assert ("U_AOI1","A1") in t and ("U_AOI2","A2") in t and ("U_AOI3","A1") in t
    netA_dbt = [x for x in t if x[0].startswith("DBT_")]
    assert len(netA_dbt) == 1
    dbt_inst = netA_dbt[0][0]
    out_net = [n for n in d.nets.values() if (dbt_inst,"Y") in n.terms][0]
    assert ("U_OAI1","B2") in out_net.terms
    assert "netB" not in d.nets and "netY" not in d.nets

def test_inverter_pair_chain_cancels():
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INV2" not in d.components and "U_INV3" not in d.components
    # XOR1 sees even parity -> direct on netP (the port net)
    assert ("U_XOR1","A") in d.nets["netP"].terms
    # no new inverter needed for this tree (netQ had no other sinks)
    dbt_on_netP = [x for x in d.nets["netP"].terms if x[0].startswith("DBT_")]
    assert dbt_on_netP == []

def test_single_necessary_inverter_survives():
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVS" in d.components
    assert d.nets["netT"].terms == [("U_INVS","Y"),("U_XOR2","A")]

def test_parallel_inverters_merge():
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVP1" not in d.components and "U_INVP2" not in d.components
    dbt = [x for x in d.nets["netp2"].terms if x[0].startswith("DBT_")]
    assert len(dbt) == 1                       # ONE shared inverter
    out = [n for n in d.nets.values() if (dbt[0][0],"Y") in n.terms][0]
    assert ("U_AOI4","A1") in out.terms and ("U_AOI5","A1") in out.terms

def test_dangling_buffer_deleted_no_insert():
    d, cfg = load()
    stats = run_dbt(d, cfg)
    assert "U_BUFD" not in d.components
    assert "netDD" not in d.nets
    assert stats.skipped_single_inv == 1       # U_INVS only (U_INVD is dead: removed)

def test_driven_dangling_single_inverter_removed():   # probe dangling_probe: Innovus deletes it
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVD" not in d.components
    assert "netD5" not in d.nets

def test_undriven_island_buffer_kept():   # probes P5/P6/P9: undriven islands untouched
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_ISL" in d.components
    assert d.nets["netISLIN"].terms == [("U_ISL","A")]

def test_even_port_tree_keeps_port_net_name():   # review finding C1
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_BUFO" not in d.components
    assert "netRA" not in d.nets                 # root name lost, port name wins
    assert set(d.nets["netOA"].terms) == {("U_NOR3","Y"),("PIN","outA")}
    assert "+ NET netOA" in d.mid                # PINS reference still valid

def test_odd_port_tree_new_inverter_takes_port_net_name():   # review finding C1
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVO" not in d.components
    dbt = [x for x in d.nets["netRB"].terms if x[0].startswith("DBT_")]
    assert len(dbt) == 1
    assert ("PIN","outB") in d.nets["netOB"].terms
    assert (dbt[0][0], "Y") in d.nets["netOB"].terms   # new INV drives the PORT net

def test_clock_tree_fully_exempt():   # NVDLA evidence: tree-level exemption
    d, cfg = load()
    s = run_dbt(d, cfg)
    assert "U_BUFC" in d.components          # clock buffer survives
    assert d.nets["netCK2"].terms == [("U_BUFC","Y"),(r"reg\[3\]","CLK")]
    assert s.skipped_clock == 1

def test_stats_totals():
    d, cfg = load()
    s = run_dbt(d, cfg)
    assert s.removed == {"U_BUF1","U_INV1","U_INV2","U_INV3","U_INVP1","U_INVP2",
                         "U_BUFD","U_BUFO","U_BUFO2","U_INVO","U_INVD"}
    assert len(s.inserted) == 3                # mixed tree + parallel merge + odd port
