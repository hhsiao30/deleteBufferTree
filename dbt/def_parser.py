import re
from dataclasses import dataclass, field

@dataclass
class Component:
    name: str
    cell: str
    tail: str = ""

@dataclass
class Net:
    name: str
    terms: list = field(default_factory=list)
    props: str = ""

@dataclass
class Design:
    header: str = ""
    components: dict = field(default_factory=dict)
    mid: str = ""
    nets: dict = field(default_factory=dict)
    footer: str = ""
    pin_names: set = field(default_factory=set)
    pin_nets: dict = field(default_factory=dict)   # port -> '+ NET' net name

_TERM = re.compile(r"\(\s*(\S+)\s+(\S+)\s*\)")

def _parse_net_stmt(stmt: str) -> Net:
    # stmt: everything from '- ' (exclusive) to ';' (exclusive), whitespace-normalized.
    # partition(" ") returns (body, "", "") when there is no space (empty net).
    body = stmt.strip()
    name, _, rest = body.partition(" ")
    plus = rest.find("+")
    termtext = rest if plus < 0 else rest[:plus]
    props = "" if plus < 0 else rest[plus:].strip()
    terms = [(a, b) for a, b in _TERM.findall(termtext)]
    return Net(name=name, terms=terms, props=props)

def parse_def(path: str) -> Design:
    text = open(path).read()
    d = Design()
    mC = re.search(r"^COMPONENTS \d+ ;\s*$", text, re.M)
    mCe = re.search(r"^END COMPONENTS\s*$", text, re.M)
    mN = re.search(r"^NETS \d+ ;\s*$", text, re.M)
    mNe = re.search(r"^END NETS\s*$", text, re.M)
    d.header = text[:mC.start()]
    comp_text = text[mC.end():mCe.start()]
    d.mid = text[mCe.end():mN.start()]
    net_text = text[mN.end():mNe.start()]
    d.footer = text[mNe.end():].lstrip("\n")

    for stmt in re.split(r"\n(?=- )", comp_text):
        stmt = stmt.strip()
        if not stmt.startswith("- "):
            continue
        body = stmt[2:].rstrip()
        if body.endswith(";"):
            body = body[:-1].rstrip()
        toks = body.split(None, 2)
        name, cell = toks[0], toks[1]
        tail = " ".join(toks[2].split()) if len(toks) > 2 else ""
        d.components[name] = Component(name, cell, tail)

    for stmt in re.split(r"\n(?=- )", net_text):
        stmt = " ".join(stmt.split())
        if not stmt.startswith("- "):
            continue
        body = stmt[2:]
        if body.endswith(";"):
            body = body[:-1].rstrip()
        n = _parse_net_stmt(body)
        d.nets[n.name] = n

    for m in re.finditer(r"^- (\S+) \+ NET (\S+)", d.mid, re.M):
        d.pin_names.add(m.group(1))
        d.pin_nets[m.group(1)] = m.group(2)
    return d
