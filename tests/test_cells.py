from dbt.cells import get_config

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

def test_tsmcn7_config_loads():
    c = get_config("tsmcn7")
    assert c.classify("BUFFD6BWP240H11P57PDULVT") == "BUF"
    assert c.classify("CKND2BWP240H11P57PDULVT") == "INV"
    assert c.classify("CKND2D1BWP240H11P57PDULVT") is None   # clock NAND2, not inverter
    assert c.classify("DCCKBD5BWP240H11P57PDULVT") == "BUF"
    assert c.new_cell == "INVD1BWP240H11P57PDULVT"
    assert "I" in c.in_pins and {"Z", "ZN"} <= c.out_pins
