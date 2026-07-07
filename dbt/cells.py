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

    def is_bi_in_pin(self, cell, pin):
        return pin in self.in_pins

    def is_bi_out_pin(self, cell, pin):
        return pin in self.out_pins

    def is_clock_pin(self, cell, pin):
        return bool(self.clock_pins) and pin in self.clock_pins

    def out_pins_of(self, cell):
        return self.out_pins | {"Y", "Z", "ZN"}

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

_TSMCN7 = NodeConfig(
    buf_patterns=['BUFFD', 'CKBD', 'BUFFSKRD', 'BUFFSKFD', 'DCCKBD'],
    inv_patterns=['INVD', 'CKND\\d+BWP', 'CKNTWBD', 'INVSKRD', 'INVSKFD', 'DCCKNTWBD', 'INVPADD', 'CKNTWAD'],
    in_pins=set(['I']),
    out_pins=set(['Z', 'ZN']),
    new_cell='INVD1BWP240H11P57PDULVT',
    new_cell_in_pin='I',
    new_cell_out_pin='ZN',
    clock_pins=set(['CLK', 'CP']),
)

def get_config(node: str) -> NodeConfig:
    if node == "asap7":
        return _ASAP7
    if node == "tsmcn7":
        return _TSMCN7
    raise KeyError(node)
