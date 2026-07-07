import json, os, re
from dataclasses import dataclass

LOCAL_TSMCN7 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "local", "tsmcn7.json")

@dataclass
class NodeConfig:
    buf_patterns: list
    inv_patterns: list
    in_pins: set
    out_pins: set
    new_cell: str
    new_cell_in_pin: str
    new_cell_out_pin: str
    clock_pins: set = None
    new_inst_prefix: str = "DBT_"
    new_net_prefix: str = "DBT_N_"

    def classify(self, cell: str):
        for p in self.inv_patterns:
            if re.match(p, cell):
                return "INV"
        for p in self.buf_patterns:
            if re.match(p, cell):
                return "BUF"
        return None

_ASAP7 = NodeConfig(
    buf_patterns=[r"BUFx", r"HB\d", r"CKBUF"],
    inv_patterns=[r"INVx", r"CKINV"],
    in_pins={"A"},
    out_pins={"Y"},
    new_cell="INVxp67_ASAP7_75t_SL",
    new_cell_in_pin="A",
    new_cell_out_pin="Y",
    clock_pins={"CLK"},
)

def get_config(node: str) -> NodeConfig:
    if node == "asap7":
        return _ASAP7
    if node == "tsmcn7":
        # NDA: full TSMC config lives in the gitignored local file
        if not os.path.exists(LOCAL_TSMCN7):
            raise FileNotFoundError(
                f"tsmcn7 config is NDA and not committed; create {LOCAL_TSMCN7} "
                "(keys: buf_patterns, inv_patterns, in_pins, out_pins, new_cell, "
                "new_cell_in_pin, new_cell_out_pin, classify_examples)")
        j = json.load(open(LOCAL_TSMCN7))
        return NodeConfig(
            buf_patterns=j["buf_patterns"], inv_patterns=j["inv_patterns"],
            in_pins=set(j["in_pins"]), out_pins=set(j["out_pins"]),
            new_cell=j["new_cell"], new_cell_in_pin=j["new_cell_in_pin"],
            new_cell_out_pin=j["new_cell_out_pin"],
            clock_pins=set(j.get("clock_pins", [])))
    raise KeyError(node)
