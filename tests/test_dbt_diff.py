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
