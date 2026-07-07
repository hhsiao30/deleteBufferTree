import subprocess, sys
from dbt.def_parser import parse_def
from dbt.def_writer import write_def
from dbt.cells import get_config
from compare.compare_dbt import compare

def _run_tool(tmp_path):
    out = tmp_path / "ours.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
                    "--output", str(out), "--node", "asap7"], check=True)
    return out

def test_self_perfect(tmp_path):
    out = _run_tool(tmp_path)
    # golden = same output but new insts/nets renamed like Innovus would
    text = out.read_text().replace("DBT_", "FE_DBTC").replace("FE_DBTCN_", "FE_OFN")
    gold = tmp_path / "gold.def"
    gold.write_text(text)
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert rep.perfect, (rep.removed_only_ours, rep.removed_only_gold,
                         rep.sink_mismatches[:5], rep.integrity_errors[:5])

def test_detects_wrong_removal(tmp_path):
    out = _run_tool(tmp_path)
    # golden that also deleted U_INVS: simulate by removing its lines from ours
    lines = [l for l in out.read_text().splitlines(True) if "U_INVS" not in l]
    gold = tmp_path / "gold.def"
    gold.write_text("".join(lines))
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert not rep.perfect
    assert "U_INVS" in rep.removed_only_gold

def test_detects_wrong_new_cell(tmp_path):        # review finding M2.1
    out = _run_tool(tmp_path)
    bad = tmp_path / "bad.def"
    bad.write_text(out.read_text().replace(
        "DBT_0 INVxp67_ASAP7_75t_SL", "DBT_0 BUFx2_ASAP7_75t_R"))
    rep = compare("tests/fixtures/mini.def", str(bad), str(out), get_config("asap7"))
    assert not rep.perfect
    assert any(e[1] == "BAD_NEW_CELL" for e in rep.integrity_errors)

def test_detects_swapped_sink_partition(tmp_path):   # Codex #2: same roots, wrong grouping
    out = _run_tool(tmp_path)
    d = parse_def(str(out))
    dbt_nets = [n for n in d.nets.values()
                if any(c.startswith("DBT_") for c, _ in n.terms) and n.name != "netOB"
                and any(c.startswith("DBT_") and p == "Y" for c, p in n.terms)]
    inv0, inv1 = dbt_nets[:2]
    moved = [t for t in inv0.terms if not t[0].startswith("DBT_")][0]
    inv0.terms.remove(moved); inv1.terms.append(moved)
    gold = tmp_path / "gold.def"; write_def(d, str(gold))
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert not rep.perfect      # sink map and sig must both flag this

def test_reused_old_net_name_is_still_perfect(tmp_path):   # Codex #6 / Innovus behavior
    # golden variant: rename a new inverter's fresh DBT_N_* output net to an OLD
    # pre-DEF net name that the rebuild deleted (Innovus does exactly this)
    out = _run_tool(tmp_path)
    text = out.read_text().replace("DBT_", "FE_DBTC").replace("FE_DBTCN_0", "netY")
    gold = tmp_path / "gold.def"; gold.write_text(text)
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert rep.perfect, (rep.sink_mismatches[:5], rep.integrity_errors[:5])
