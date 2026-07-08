import subprocess, sys

def _run_tool(tmp_path):
    out = tmp_path / "post.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
                    "--output", str(out), "--node", "asap7"], check=True)
    return out

def test_diff_report(tmp_path):
    post = _run_tool(tmp_path)
    r = subprocess.run([sys.executable, "compare/dbt_diff.py",
                        "--pre", "tests/fixtures/mini.def", "--post", str(post),
                        "--node", "asap7"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    t = r.stdout
    assert "removed=11" in t and "inserted=3" in t
    assert "BUF" in t and "INV" in t
    assert "survivors with CELL changed: 0" in t
    assert "clean (PINS refs valid" in t
    assert "merge factor" in t


PRE_BUFDRV = """VERSION 5.8 ;
DIVIDERCHAR "/" ;
BUSBITCHARS "[]" ;
DESIGN t ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 1000 1000 ) ;
COMPONENTS 4 ;
- U_NOR NOR2x1_ASAP7_75t_SL + PLACED ( 10 10 ) N ;
- U_I INVx1_ASAP7_75t_R + PLACED ( 20 10 ) N ;
- U_B BUFx2_ASAP7_75t_R + PLACED ( 30 10 ) N ;
- U_G AOI22xp5_ASAP7_75t_R + PLACED ( 40 10 ) N ;
END COMPONENTS
PINS 0 ;
END PINS
NETS 4 ;
- n1 ( U_NOR Y ) ( U_I A ) ;
- n2 ( U_I Y ) ( U_B A ) ;
- n3 ( U_B Y ) ( U_G A1 ) ;
END NETS
END DESIGN
"""

def test_merge_factor_ignores_buffer_drivers(tmp_path):
    # root -> INV -> BUF -> sink : odd-parity sink, its immediate PRE driver is a BUF.
    # the inserted inverter must report absorbed=0 (buffers are not inverters).
    pre = tmp_path / "pre.def"; pre.write_text(PRE_BUFDRV)
    post = tmp_path / "post.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", str(pre),
                    "--output", str(post), "--node", "asap7"], check=True)
    r = subprocess.run([sys.executable, "compare/dbt_diff.py",
                        "--pre", str(pre), "--post", str(post), "--node", "asap7"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "absorbed  0 old INVs :       1" in r.stdout, r.stdout
