import subprocess, sys

def test_two_runs_identical(tmp_path):
    outs = []
    for i in range(2):
        o = tmp_path / f"o{i}.def"
        subprocess.run([sys.executable, "-m", "dbt.cli", "--input",
                        "tests/fixtures/mini.def", "--output", str(o),
                        "--node", "asap7"], check=True)
        outs.append(o.read_bytes())
    assert outs[0] == outs[1]
