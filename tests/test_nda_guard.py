import subprocess, re

def test_no_tsmc_cell_names_tracked():
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
    offenders = []
    for f in files:
        try:
            if re.search(r"BWP\d", open(f, errors="ignore").read()):
                offenders.append(f)
        except IsADirectoryError:
            pass
    assert not offenders, f"NDA: full TSMC cell names tracked in {offenders}"
