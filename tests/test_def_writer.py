from dbt.def_parser import parse_def, Component, Net
from dbt.def_writer import write_def

def test_roundtrip(tmp_path):
    d = parse_def("tests/fixtures/mini.def")
    out = tmp_path / "rt.def"
    write_def(d, str(out))
    d2 = parse_def(str(out))
    assert list(d2.components) == list(d.components)
    assert all(d2.components[k].cell == d.components[k].cell for k in d.components)
    assert {k: v.terms for k, v in d2.nets.items()} == {k: v.terms for k, v in d.nets.items()}
    assert d2.pin_names == d.pin_names

def test_unplaced_component_style(tmp_path):
    d = parse_def("tests/fixtures/mini.def")
    # new insts carry '+ SOURCE TIMING' like Innovus's FE_DBTC (review finding m3)
    d.components["DBT_0"] = Component("DBT_0", "INVxp67_ASAP7_75t_SL", "+ SOURCE TIMING")
    d.nets["DBT_N_0"] = Net("DBT_N_0", [("DBT_0", "Y"), ("U_XOR2", "B")], "")
    out = tmp_path / "u.def"
    write_def(d, str(out))
    text = out.read_text()
    assert "- DBT_0 INVxp67_ASAP7_75t_SL + SOURCE TIMING ;" in text
    assert "COMPONENTS 31 ;" in text
    assert "NETS 26 ;" in text
