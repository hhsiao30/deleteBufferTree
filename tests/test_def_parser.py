from dbt.def_parser import parse_def

def test_parse_mini():
    d = parse_def("tests/fixtures/mini.def")
    assert len(d.components) == 28
    assert d.components["U_BUF1"].cell == "BUFx2_ASAP7_75t_R"
    assert d.components[r"reg\[3\]"].cell == "DFFASRHQNx1_ASAP7_75t_R"
    assert "+ PLACED ( 200 100 ) N" in d.components["U_BUF1"].tail
    assert len(d.nets) == 21
    assert d.nets["netA"].terms == [("U_NAND","Y"),("U_BUF1","A"),("U_INV1","A"),("U_AOI3","A1")]
    assert d.nets["netA"].props.strip() == "+ SOURCE TIMING"
    assert d.nets["netP"].terms[0] == ("PIN","in1")
    assert d.nets["netEMPTY"].terms == []
    assert d.pin_names == {"in1","outA","outB"}
    assert d.pin_nets["outA"] == "netOA"
    assert "VERSION 5.8 ;" in d.header          # header may start with a # banner
    assert "PINS 4 ;" in d.mid
    assert "vddp" not in d.pin_nets            # PG pins excluded (USE POWER/GROUND)
    assert d.footer.strip() == "END DESIGN"
