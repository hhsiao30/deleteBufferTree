import json, os, pytest
from dbt.cells import get_config, LOCAL_TSMCN7

def test_asap7_classify():
    c = get_config("asap7")
    assert c.classify("BUFx2_ASAP7_75t_R") == "BUF"
    assert c.classify("HB1xp67_ASAP7_75t_R") == "BUF"      # hold buffers are buffers
    assert c.classify("INVx4_ASAP7_75t_L") == "INV"
    assert c.classify("INVxp67_ASAP7_75t_SL") == "INV"
    assert c.classify("CKINVDCx16_ASAP7_75t_SL") == "INV"  # review finding M1
    assert c.classify("CKBUFx4_ASAP7_75t_R") == "BUF"
    assert c.classify("NAND2xp5_ASAP7_75t_R") is None
    assert c.classify("DFFASRHQNx1_ASAP7_75t_R") is None
    assert c.new_cell == "INVxp67_ASAP7_75t_SL"
    assert c.new_cell_in_pin == "A" and c.new_cell_out_pin == "Y"

@pytest.mark.skipif(not os.path.exists(LOCAL_TSMCN7), reason="local tsmcn7 config absent")
def test_tsmcn7_config_loads():
    # NDA: assert against strings read from the local (gitignored) file, no literals here
    cfgj = json.load(open(LOCAL_TSMCN7))
    c = get_config("tsmcn7")
    assert c.new_cell == cfgj["new_cell"]
    for cell, want in cfgj.get("classify_examples", {}).items():
        assert c.classify(cell) == (want or None)
    assert "I" in c.in_pins and {"Z", "ZN"} <= c.out_pins
