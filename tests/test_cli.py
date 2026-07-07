import subprocess, sys

def test_cli_mini(tmp_path):
    out = tmp_path / "out.def"
    r = subprocess.run(
        [sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
         "--output", str(out), "--node", "asap7"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "removed=10" in r.stdout and "inserted=3" in r.stdout
    assert out.exists()
