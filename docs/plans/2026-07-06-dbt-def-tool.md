# DEF-in / DEF-out deleteBufferTree Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Python tool that reads a placed pre-CTS DEF, performs Innovus-equivalent `deleteBufferTree`, writes a DEF, and a structural comparator that proves the output matches Innovus golden outputs on asap7 + tsmcn7 ariane.

**Architecture:** Three units — (1) a minimal DEF parser/writer that understands COMPONENTS/PINS/NETS and passes every other section through verbatim; (2) the core tree-rebuild algorithm implementing the empirically-verified rule (per-root-net tree; rebuild iff it strictly reduces cell count; even-parity sinks reattach to root, odd-parity sinks share ONE new minimal inverter); (3) a name-agnostic structural comparator that maps every sink pin to a `(root_net, parity)` signature and diffs our output against the Innovus golden.

**Tech Stack:** Python 3.9+ stdlib only (re, argparse, dataclasses). No LEF/lib parsing — cell classification via per-node config (regex patterns + pin roles), which is exactly the information `deleteBufferTree` needs.

## Global Constraints

- Repo root: `/nethome/hhsiao30/asap7/dbt_tool/` — its own local git repo (`git init`), code + tiny synthetic fixtures only.
- **NDA: never copy tsmcn7 DEF content (cell names, coordinates) into this repo, tests, fixtures, OR THIS PLAN FILE.** The entire tsmcn7 `NodeConfig` (patterns AND the replacement cell name) lives in gitignored `local/tsmcn7.json`; `get_config("tsmcn7")` loads it and raises a clear error if absent. Committed files may contain at most TSMC family prefixes (`BUFFD`, `CKBD`, `CKND`, `INVD`, `DCCKND`) — never full cell names. A committed guard test (`tests/test_nda_guard.py`) asserts no tracked file matches `BWP\d`. tsmcn7 goldens referenced by absolute path at runtime only; only counts may be quoted in reports.
- Golden files (already exist, read-only):
  - asap7 input: `/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_ariane/result/ariane/ariane_pre_deleteBufferTree.def`
  - asap7 golden: `.../ariane_post_deleteBufferTree_withUnplaced.def` (97,897 comps incl. 1,703 unplaced FE_DBTC)
  - tsmcn7 input/golden: same filenames under `/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_tsmcn7_ariane/result/ariane/` (126,039 → 113,729 incl. 2,216 unplaced)
- Names are raw DEF tokens (backslash escapes kept verbatim, e.g. `foo\[3\]`); never unescape. DEF tokens never contain whitespace → whitespace tokenization is safe.
- Match criterion (agreed): **structural equivalence, not byte equality.** New instance names differ by construction (Innovus: `FE_DBTC*`; ours: `DBT_*`). Verdict comes from the comparator, not `diff`.
- **Net-identity rule (adversarial-review finding C1, verified against golden):** Innovus never renames a port's net — 0 of 443 PINS `+ NET` references changed, and all 1,703 inserted-inverter output nets REUSE pre-DEF net names. Therefore: when a rebuild would delete a net referenced by a PINS `+ NET`, that name must win — an even-parity port sink group renames the merged root net to the port net's name; an odd-parity port sink names the new inverter's output net with the port net's name. Without this rule the output DEF dangles 224 port references on asap7 and PERFECT is unreachable.
- Empirical rule reference (verified 2026-07-06, this session): buffers 100% removed; isolated single necessary inverter untouched; per-tree rebuild with sink-parity groups; one shared minimal inverter per tree's odd group; new inverter cell is fixed per node (asap7: `INVxp67_ASAP7_75t_SL`). Open questions the comparator must adjudicate: (a) does Innovus ever split a huge odd group into >1 inverter? (b) the 32 "other" cases from the classification; (c) exact treatment of dangling/portsink corners.
- **Netlist-stage scope (deliberate): pre-CTS `place_opt` exports ONLY.** (1) The DEF and the netlist that generated its golden must be the same-stage export pair. (2) This is deleteBufferTree's native invocation point AND the stage where the clock-path exemption is an empty set (no clock tree yet) — a DEF-only tool has no timing graph and cannot identify clock paths, so post-CTS netlists are OUT of scope (future work: SDC clock-root cone approximation). All 13 corpus designs are place_opt-stage exports (verified 2026-07-07 preflight: 6 asap7 `<d>_fixed.v`+DEF, 7 tsmcn7 complete).

## File Structure

```
dbt_tool/
├── docs/plans/2026-07-06-dbt-def-tool.md   (this file)
├── dbt/
│   ├── __init__.py
│   ├── cells.py        # per-node cell classification config
│   ├── def_parser.py   # DEF → Design
│   ├── def_writer.py   # Design → DEF text
│   ├── core.py         # tree detection + rebuild
│   └── cli.py          # python -m dbt.cli --in X.def --out Y.def --node asap7
├── compare/
│   └── compare_dbt.py  # structural comparator (pre, ours, golden) → report
├── tests/
│   ├── fixtures/mini.def
│   ├── test_cells.py
│   ├── test_def_parser.py
│   ├── test_def_writer.py
│   ├── test_core.py
│   └── test_compare.py
└── .gitignore          # local/, __pycache__, *.pyc, out/
```

Data model (shared by all units, defined in `def_parser.py`):

```python
@dataclass
class Component:
    name: str
    cell: str
    tail: str          # raw text after cell name up to ';' (placement etc.), '' for new insts

@dataclass
class Net:
    name: str
    terms: list        # [(comp_or_'PIN', pin_or_pinname)] raw tokens
    props: str         # raw '+ ...' text after terms, e.g. '+ SOURCE TIMING'

@dataclass
class Design:
    header: str        # verbatim text before COMPONENTS
    components: dict   # name -> Component (insertion-ordered)
    mid: str           # verbatim text between END COMPONENTS and NETS (incl. PINS section)
    nets: dict         # name -> Net (insertion-ordered)
    footer: str        # verbatim text after END NETS
    pin_names: set     # top-level port names parsed from PINS inside mid
```

---

### Task 1: Repo scaffold + cell classification config

**Files:**
- Create: `.gitignore`, `dbt/__init__.py`, `dbt/cells.py`
- Test: `tests/test_cells.py`

**Interfaces:**
- Produces: `class NodeConfig` with fields `buf_patterns: list[str]`, `inv_patterns: list[str]`, `in_pins: set[str]`, `out_pins: set[str]`, `new_cell: str`, `new_cell_in_pin: str`, `new_cell_out_pin: str`, `new_inst_prefix: str = "DBT_"`, `new_net_prefix: str = "DBT_N_"`; functions `get_config(node: str) -> NodeConfig`, method `cfg.classify(cell_name) -> 'BUF'|'INV'|None`.

- [ ] **Step 1: git init + .gitignore + NDA guard test**

```bash
cd /nethome/hhsiao30/asap7/dbt_tool
git init
printf 'local/\n__pycache__/\n*.pyc\nout/\n' > .gitignore
mkdir -p local
touch dbt/__init__.py
```

```python
# tests/test_nda_guard.py
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
```

```bash
git add .gitignore dbt/__init__.py tests/test_nda_guard.py docs/plans/2026-07-06-dbt-def-tool.md
git commit -m "chore: scaffold dbt_tool repo with plan and NDA guard"
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_cells.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /nethome/hhsiao30/asap7/dbt_tool && python3 -m pytest tests/test_cells.py -q`
Expected: FAIL (`ModuleNotFoundError: dbt.cells`)

- [ ] **Step 4: Implement dbt/cells.py**

```python
# dbt/cells.py
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
            new_cell_out_pin=j["new_cell_out_pin"])
    raise KeyError(node)
```

Also in this task (uncommitted, gitignored): write `local/tsmcn7.json` with the
family patterns validated so far — inv: `INVD`, `CKND`, `CKNTWBD`, skew-cell
inverter families; buf: `BUFFD`, `CKBD` (delay families like `DCCKND`/`DEL`
excluded: SPECIAL timing arcs); pins I/Z/ZN; `new_cell` = the minimal D1 ULVT
inverter observed in the golden; `new_cell_out_pin` = `ZN`. Exact strings come
from the golden DEF on /cedar — do not copy them from this plan (they are not
here, deliberately). Task 8's removed-set diff is the authority for correcting
patterns (adversarial review measured: first-pass config misses 919 instances
across 7 families on tsmcn7 — expect several correction rounds).

Ordering note: `inv_patterns` are tested before `buf_patterns` (so an inverter
family is never swallowed by a broader buffer pattern).

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cells.py tests/test_nda_guard.py -q`
Expected: 3 passed (2 passed + 1 skipped until `local/tsmcn7.json` is written; after writing it: 3 passed). NDA guard must pass — if it fails, a full TSMC name leaked into a tracked file.

- [ ] **Step 6: Commit**

```bash
git add dbt/cells.py tests/test_cells.py
git commit -m "feat: per-node buffer/inverter classification config (tsmcn7 via gitignored local json)"
```

---

### Task 2: DEF parser (COMPONENTS/PINS/NETS subset, verbatim passthrough)

**Files:**
- Create: `dbt/def_parser.py`, `tests/fixtures/mini.def`
- Test: `tests/test_def_parser.py`

**Interfaces:**
- Produces: `parse_def(path: str) -> Design` (Design/Component/Net dataclasses as in the plan header). `Design.components` and `Design.nets` are `dict[str, ...]` preserving file order. `Net.terms` items are `(comp_name, pin)` tuples; top-level port terms are `("PIN", portname)`.

- [ ] **Step 1: Write the synthetic fixture (hand-authored, models real Innovus output shapes)**

```
# tests/fixtures/mini.def  — topology summary:
#  netA: NAND (kept logic) -> [BUF1 -> {AOI1, AOI2}], [INV1 -> {OAI1}], AOI3 direct   (mixed tree)
#  netP: PIN in1 -> INV2 -> INV3 -> {XOR1}                                            (inverter pair chain)
#  netS: NOR1 -> INVS -> {XOR2}                                                       (isolated single INV: must survive)
#  netp2: NAND2b -> INVP1 -> {AOI4}, INVP2 -> {AOI5}                                  (parallel INVs: merge)
#  netD: NOR2 -> BUFD (no sinks)                                                      (dangling buffer: delete, insert nothing)
#  escaped name coverage: reg\[3\] instance
VERSION 5.8 ;
DIVIDERCHAR "/" ;
BUSBITCHARS "[]" ;
DESIGN mini ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
COMPONENTS 18 ;
- U_NAND NAND2xp5_ASAP7_75t_R + PLACED ( 100 100 ) N ;
- U_BUF1 BUFx2_ASAP7_75t_R + PLACED ( 200 100 ) N ;
- U_INV1 INVx4_ASAP7_75t_L + PLACED ( 300 100 ) N ;
- U_AOI1 AOI22xp5_ASAP7_75t_R + PLACED ( 400 100 ) N ;
- U_AOI2 AOI22xp5_ASAP7_75t_L + PLACED ( 500 100 ) N ;
- U_AOI3 AOI22xp5_ASAP7_75t_R + PLACED ( 600 100 ) N ;
- U_OAI1 OAI22x1_ASAP7_75t_R + PLACED ( 700 100 ) N ;
- U_INV2 INVx1_ASAP7_75t_R + PLACED ( 200 200 ) N ;
- U_INV3 INVx2_ASAP7_75t_R + PLACED ( 300 200 ) N ;
- U_XOR1 XOR2xp5_ASAP7_75t_L + PLACED ( 400 200 ) N ;
- U_NOR1 NOR2x1_ASAP7_75t_SL + PLACED ( 100 300 ) N ;
- U_INVS INVx3_ASAP7_75t_R + PLACED ( 200 300 ) N ;
- U_XOR2 XOR2xp5_ASAP7_75t_L + PLACED ( 300 300 ) N ;
- U_NAND2b NAND2xp5_ASAP7_75t_R + PLACED ( 100 400 ) N ;
- U_INVP1 INVx1_ASAP7_75t_R + PLACED ( 200 400 ) N ;
- U_INVP2 INVx2_ASAP7_75t_L + PLACED ( 200 450 ) N ;
- U_AOI4 AOI22xp5_ASAP7_75t_R + PLACED ( 300 400 ) N ;
- U_AOI5 AOI22xp5_ASAP7_75t_R + PLACED ( 300 450 ) N ;
- U_NOR2 NOR2x1_ASAP7_75t_SL + PLACED ( 100 500 ) N ;
- U_BUFD BUFx2_ASAP7_75t_R + PLACED ( 200 500 ) N ;
- reg\[3\] DFFASRHQNx1_ASAP7_75t_R + PLACED ( 600 500 ) N ;
- U_NOR3 NOR2x1_ASAP7_75t_SL + PLACED ( 100 600 ) N ;
- U_BUFO BUFx2_ASAP7_75t_R + PLACED ( 200 600 ) N ;
- U_NAND3 NAND2xp5_ASAP7_75t_R + PLACED ( 100 700 ) N ;
- U_BUFO2 BUFx2_ASAP7_75t_R + PLACED ( 150 700 ) N ;
- U_INVO INVx1_ASAP7_75t_R + PLACED ( 200 700 ) N ;
- U_NOR4 NOR2x1_ASAP7_75t_SL + PLACED ( 100 800 ) N ;
- U_INVD INVx2_ASAP7_75t_R + PLACED ( 200 800 ) N ;
END COMPONENTS
PINS 3 ;
- in1 + NET netP + DIRECTION INPUT + USE SIGNAL
  + LAYER M5 ( -12 0 ) ( 12 84 )
  + PLACED ( 0 200 ) N ;
- outA + NET netOA + DIRECTION OUTPUT + USE SIGNAL
  + LAYER M5 ( -12 0 ) ( 12 84 )
  + PLACED ( 10000 600 ) N ;
- outB + NET netOB + DIRECTION OUTPUT + USE SIGNAL
  + LAYER M5 ( -12 0 ) ( 12 84 )
  + PLACED ( 10000 700 ) N ;
END PINS
NETS 12 ;
- netA ( U_NAND Y ) ( U_BUF1 A ) ( U_INV1 A ) ( U_AOI3 A1 )
  + SOURCE TIMING ;
- netB ( U_BUF1 Y ) ( U_AOI1 A1 ) ( U_AOI2 A2 ) ;
- netY ( U_INV1 Y ) ( U_OAI1 B2 ) ;
- netP ( PIN in1 ) ( U_INV2 A ) ;
- netQ ( U_INV2 Y ) ( U_INV3 A ) ;
- netR ( U_INV3 Y ) ( U_XOR1 A ) ;
- netS ( U_NOR1 Y ) ( U_INVS A ) ;
- netT ( U_INVS Y ) ( U_XOR2 A ) ;
- netp2 ( U_NAND2b Y ) ( U_INVP1 A ) ( U_INVP2 A ) ;
- netU ( U_INVP1 Y ) ( U_AOI4 A1 ) ;
- netV ( U_INVP2 Y ) ( U_AOI5 A1 ) ;
- netD ( U_NOR2 Y ) ( U_BUFD A ) ;
- netDD ( U_BUFD Y ) ;
- netRA ( U_NOR3 Y ) ( U_BUFO A ) ;
- netOA ( U_BUFO Y ) ( PIN outA ) ;
- netRB ( U_NAND3 Y ) ( U_BUFO2 A ) ;
- netRB2 ( U_BUFO2 Y ) ( U_INVO A ) ;
- netOB ( U_INVO Y ) ( PIN outB ) ;
- netD4 ( U_NOR4 Y ) ( U_INVD A ) ;
- netD5 ( U_INVD Y ) ;
- netEMPTY ;
END NETS
END DESIGN
```

Fixture adds (review findings C1/M3 + Codex #4): `netRA→BUFO→outA` = even-parity
OUTPUT-port tree; `netRB→INVO→outB` = odd-parity output-port tree; `U_INVD` =
DANGLING single inverter (must SURVIVE — golden evidence: Innovus keeps 5 such);
`netEMPTY` = empty net.
(Count lines are deliberately understated — 18 vs 28 components, 12 vs 21 nets:
the parser must not trust count headers; it parses to `END COMPONENTS`/`END NETS`.
The `#` comment banner stays in the file — DEF permits `#` comments and the real
Innovus DEFs start with one, so `header` will not start with `VERSION`.)

- [ ] **Step 2: Write the failing test**

```python
# tests/test_def_parser.py
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
    assert "VERSION 5.8 ;" in d.header          # header may start with a # banner
    assert "PINS 3 ;" in d.mid
    assert d.footer.strip() == "END DESIGN"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_def_parser.py -q`
Expected: FAIL (`ModuleNotFoundError: dbt.def_parser`)

- [ ] **Step 4: Implement dbt/def_parser.py**

```python
# dbt/def_parser.py
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
    # partition(" ") returns (body, "", "") when there is no space (empty net) —
    # never pass None (review finding M3).
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
        tail = toks[2] if len(toks) > 2 else ""
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
```

`Design` gains one field used by the core's net-identity rule (C1):
`pin_nets: dict = field(default_factory=dict)` — port name → its `+ NET` net
name from the PINS section. Add `assert d.pin_nets["outA"] == "netOA"` to
`test_parse_mini`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_def_parser.py -q`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add dbt/def_parser.py tests/fixtures/mini.def tests/test_def_parser.py
git commit -m "feat: minimal DEF parser (components/pins/nets + passthrough)"
```

---

### Task 3: DEF writer + parse→write→parse roundtrip

**Files:**
- Create: `dbt/def_writer.py`
- Test: `tests/test_def_writer.py`

**Interfaces:**
- Consumes: `Design` from `dbt.def_parser`.
- Produces: `write_def(d: Design, path: str) -> None`. Components with `tail == ""` are written as `- name cell ;` (matches Innovus unplaced style minus SOURCE prop). COMPONENTS/NETS counts recomputed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_def_writer.py
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
    assert "COMPONENTS 29 ;" in text
    assert "NETS 22 ;" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_def_writer.py -q`
Expected: FAIL (`ModuleNotFoundError: dbt.def_writer`)

- [ ] **Step 3: Implement dbt/def_writer.py**

```python
# dbt/def_writer.py
from .def_parser import Design

def _comp_line(c) -> str:
    if c.tail:
        return f"- {c.name} {c.cell} {c.tail} ;"
    return f"- {c.name} {c.cell} ;"

def _net_lines(n) -> str:
    parts = [f"- {n.name}"]
    parts += [f"  ( {a} {b} )" for a, b in n.terms]
    if n.props:
        parts.append(f"  {n.props}")
    return "\n".join(parts) + "\n ;"

def write_def(d: Design, path: str) -> None:
    with open(path, "w") as f:
        f.write(d.header)
        f.write(f"COMPONENTS {len(d.components)} ;\n")
        for c in d.components.values():
            f.write(_comp_line(c) + "\n")
        f.write("END COMPONENTS\n")
        f.write(d.mid)
        f.write(f"NETS {len(d.nets)} ;\n")
        for n in d.nets.values():
            f.write(_net_lines(n) + "\n")
        f.write("END NETS\n")
        f.write(d.footer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_def_writer.py -q`
Expected: 2 passed

- [ ] **Step 5: Roundtrip smoke on the real asap7 pre DEF (integration, not committed as fixture)**

Run:
```bash
python3 - <<'EOF'
from dbt.def_parser import parse_def
from dbt.def_writer import write_def
d = parse_def("/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_ariane/result/ariane/ariane_pre_deleteBufferTree.def")
assert len(d.components) == 105730, len(d.components)
write_def(d, "/tmp/rt.def")
d2 = parse_def("/tmp/rt.def")
assert len(d2.components) == 105730 and len(d2.nets) == len(d.nets)
print("roundtrip OK", len(d.nets))
EOF
```
Expected: `roundtrip OK 108830`

- [ ] **Step 6: Commit**

```bash
git add dbt/def_writer.py tests/test_def_writer.py
git commit -m "feat: DEF writer with recomputed counts and unplaced style"
```

---

### Task 4: Core algorithm — tree detection + rebuild

**Files:**
- Create: `dbt/core.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `Design`, `NodeConfig`.
- Produces: `run_dbt(d: Design, cfg: NodeConfig) -> DbtStats` mutating `d` in place. `DbtStats` dataclass: `removed: set[str]`, `inserted: list[str]`, `skipped_single_inv: int`, `trees: int`.

Algorithm (locked-in from the verified empirical rule):

1. Classify every component: `kind[name] = cfg.classify(cell)`; BI candidates = {name: kind != None}.
2. Index in TWO passes (Codex review finding #5): first collect `in_net`/`out_net` for every BI candidate; a candidate is a **valid BI** only if BOTH its input net and output net were recognized — candidates missing either (mis-modeled pin roles, dangling pins) go to `stats.degenerate` and are treated as ordinary logic everywhere (they must NOT populate `bi_driver`, or they would silently block root detection downstream — a real hazard while tsmcn7 pin roles are still being tuned). Then build `bi_loads(net)` / `bi_driver(net)` from valid BIs only.
3. Tree roots: a net R is a root iff `bi_loads(R)` non-empty **and** `bi_driver(R)` is None.
4. Tree membership: BFS from R through BI insts: member m ∈ tree(R) if m's input net is R or the output net of another member. Record `parity(m)` = (# of INV on path from R, inclusive of m if INV) and `out_net(m)`.
5. Sinks: for every member m, every term on `out_net(m)` that is **not** (member, in-pin of member): sink with `parity = parity(m) % 2`. Terms include `("PIN", port)` — ports are sinks like any other. (The root net's own non-BI loads stay put; they are not sinks of the tree.)
6. Decision: if tree members == exactly one INV → skip (stats.skipped_single_inv += 1), **regardless of whether it has sinks**. (Codex review argued a sink-less dangling INV should be deleted for the count gain — REFUTED by golden evidence: the asap7 golden keeps 5 dangling inverters. Innovus's actual rule is "never touch a single-INV tree", and matching Innovus is the goal.) Else rebuild:
   - delete all members from `d.components`; delete each `out_net(m)` from `d.nets`.
   - even-parity sinks: append to `d.nets[R].terms`.
   - odd-parity sinks (if any): create inst `DBT_<i>` (cell `cfg.new_cell`, tail `"+ SOURCE TIMING"`) + a new net with terms `[(DBT_<i>, cfg.new_cell_out_pin), *odd_sinks]`, and append `(DBT_<i>, cfg.new_cell_in_pin)` to `d.nets[R].terms`.
7. **Net-identity rule (C1):** compute `port_nets = set(d.pin_nets.values())` once.
   - If any deleted `out_net(m)` ∈ `port_nets` whose `(PIN, p)` sink is EVEN-parity: after the merge, RENAME the root net record to that port net's name (keep the root's props; drop the old root name). If several distinct even-parity port nets merge, keep the first and rewrite the other ports' `+ NET` references inside `d.mid` (regex `- <port> + NET <old>` → `+ NET <kept>`); count rewrites in `stats.pin_net_rewrites`.
   - The odd-sink net's NAME: if the odd group contains `(PIN, p)` terms, use `d.pin_nets[p]` (the port's net name) instead of `DBT_N_<i>`; else `DBT_N_<i>` is fine (Innovus reuses old sink-side net names; the comparator is name-agnostic for non-port new nets, so we only MUST match port-net names).
   - Root nets that are port nets (input ports) already keep their names — no action.
8. Dedup: a net that is out_net of member A and also root-like for member B is internal — handled naturally since B ∈ tree(R). A BI inst with no input net or no output net (degenerate) → treat as non-member (classify but never traverse); count in `stats` as `degenerate`.

- [ ] **Step 1: Write the failing tests (one per topology in mini.def)**

```python
# tests/test_core.py
from dbt.def_parser import parse_def
from dbt.cells import get_config
from dbt.core import run_dbt

def load():
    d = parse_def("tests/fixtures/mini.def")
    return d, get_config("asap7")

def test_mixed_tree_rebuild():
    d, cfg = load()
    run_dbt(d, cfg)
    # BUF1/INV1 deleted; AOI1,AOI2 direct on netA; OAI1 behind one new inverter
    assert "U_BUF1" not in d.components and "U_INV1" not in d.components
    t = d.nets["netA"].terms
    assert ("U_AOI1","A1") in t and ("U_AOI2","A2") in t and ("U_AOI3","A1") in t
    new_invs = [c for c in d.components.values() if c.name.startswith("DBT_")]
    netA_dbt = [x for x in t if x[0].startswith("DBT_")]
    assert len(netA_dbt) == 1
    dbt_inst = netA_dbt[0][0]
    out_net = [n for n in d.nets.values() if (dbt_inst,"Y") in n.terms][0]
    assert ("U_OAI1","B2") in out_net.terms
    assert "netB" not in d.nets and "netY" not in d.nets

def test_inverter_pair_chain_cancels():
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INV2" not in d.components and "U_INV3" not in d.components
    # XOR1 sees even parity -> direct on netP (the port net)
    assert ("U_XOR1","A") in d.nets["netP"].terms
    # no new inverter needed for this tree (netQ had no other sinks)
    dbt_on_netP = [x for x in d.nets["netP"].terms if x[0].startswith("DBT_")]
    assert dbt_on_netP == []

def test_single_necessary_inverter_survives():
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVS" in d.components
    assert d.nets["netT"].terms == [("U_INVS","Y"),("U_XOR2","A")]

def test_parallel_inverters_merge():
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVP1" not in d.components and "U_INVP2" not in d.components
    dbt = [x for x in d.nets["netp2"].terms if x[0].startswith("DBT_")]
    assert len(dbt) == 1                       # ONE shared inverter
    out = [n for n in d.nets.values() if (dbt[0][0],"Y") in n.terms][0]
    assert ("U_AOI4","A1") in out.terms and ("U_AOI5","A1") in out.terms

def test_dangling_buffer_deleted_no_insert():
    d, cfg = load()
    stats = run_dbt(d, cfg)
    assert "U_BUFD" not in d.components
    assert "netDD" not in d.nets
    assert stats.skipped_single_inv == 2       # U_INVS + U_INVD trees

def test_dangling_single_inverter_survives():   # Codex #4, refuted by golden: keep it
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVD" in d.components
    assert d.nets["netD5"].terms == [("U_INVD","Y")]

def test_even_port_tree_keeps_port_net_name():   # review finding C1
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_BUFO" not in d.components
    assert "netRA" not in d.nets                 # root name lost, port name wins
    assert set(d.nets["netOA"].terms) == {("U_NOR3","Y"),("PIN","outA")}
    assert "+ NET netOA" in d.mid                # PINS reference still valid

def test_odd_port_tree_new_inverter_takes_port_net_name():   # review finding C1
    d, cfg = load()
    run_dbt(d, cfg)
    assert "U_INVO" not in d.components
    dbt = [x for x in d.nets["netRB"].terms if x[0].startswith("DBT_")]
    assert len(dbt) == 1
    assert ("PIN","outB") in d.nets["netOB"].terms
    assert (dbt[0][0], "Y") in d.nets["netOB"].terms   # new INV drives the PORT net

def test_stats_totals():
    d, cfg = load()
    s = run_dbt(d, cfg)
    assert s.removed == {"U_BUF1","U_INV1","U_INV2","U_INV3","U_INVP1","U_INVP2",
                         "U_BUFD","U_BUFO","U_BUFO2","U_INVO"}
    assert len(s.inserted) == 3                # mixed tree + parallel merge + odd port
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_core.py -q`
Expected: FAIL (`ModuleNotFoundError: dbt.core`)

- [ ] **Step 3: Implement dbt/core.py**

```python
# dbt/core.py
from dataclasses import dataclass, field
from collections import defaultdict, deque
from .def_parser import Component, Net

@dataclass
class DbtStats:
    removed: set = field(default_factory=set)
    inserted: list = field(default_factory=list)
    skipped_single_inv: int = 0
    trees: int = 0
    degenerate: int = 0
    pin_net_rewrites: int = 0

def run_dbt(d, cfg) -> DbtStats:
    stats = DbtStats()
    kind = {}
    for name, c in d.components.items():
        k = cfg.classify(c.cell)
        if k:
            kind[name] = k

    in_net = {}    # BI inst -> its input net
    out_net = {}   # BI inst -> its output net
    for n in d.nets.values():
        for comp, pin in n.terms:
            if comp in kind:
                if pin in cfg.in_pins:
                    in_net[comp] = n.name
                elif pin in cfg.out_pins:
                    out_net[comp] = n.name
    # valid BI = both pins recognized; others are degenerate and act as logic
    invalid = {c for c in kind if c not in in_net or c not in out_net}
    stats.degenerate = len(invalid)
    for c in invalid:
        kind.pop(c); in_net.pop(c, None); out_net.pop(c, None)
    bi_loads = defaultdict(list)   # net -> [BI inst]
    bi_driver = {}                 # net -> BI inst
    for c in kind:
        bi_loads[in_net[c]].append(c)
        bi_driver[out_net[c]] = c

    counter = 0
    port_net_of = {}   # net name -> port name (for the C1 naming rule)
    for p, n in d.pin_nets.items():
        port_net_of[n] = p
    for R in list(d.nets):
        if not bi_loads.get(R) or bi_driver.get(R):
            continue   # not a root: no BI loads, or driven by a BI cell (internal net)
        # BFS collect members
        members = []          # (inst, parity_below)  parity counts INV on path incl. self
        q = deque((b, 0) for b in bi_loads[R])
        seen = set()
        while q:
            inst, par_above = q.popleft()
            if inst in seen or inst not in d.components:
                continue
            seen.add(inst)
            if inst not in out_net or inst not in in_net:
                stats.degenerate += 1
                continue
            par = par_above + (1 if kind[inst] == "INV" else 0)
            members.append((inst, par))
            for child in bi_loads.get(out_net[inst], []):
                q.append((child, par))
        if not members:
            continue
        stats.trees += 1
        if len(members) == 1 and kind[members[0][0]] == "INV":
            stats.skipped_single_inv += 1
            continue
        member_set = {m for m, _ in members}
        even_sinks, odd_sinks = [], []
        even_port_nets, odd_port_nets = [], []
        for inst, par in members:
            onet = d.nets.get(out_net[inst])
            if onet is None:
                continue
            is_port_net = onet.name in port_net_of
            for comp, pin in onet.terms:
                if comp == inst and pin in cfg.out_pins:
                    continue
                if comp in member_set and pin in cfg.in_pins:
                    continue
                if par % 2:
                    odd_sinks.append((comp, pin))
                    if is_port_net and comp == "PIN":
                        odd_port_nets.append(onet.name)
                else:
                    even_sinks.append((comp, pin))
                    if is_port_net and comp == "PIN":
                        even_port_nets.append(onet.name)
        for inst, _ in members:
            stats.removed.add(inst)
            del d.components[inst]
            d.nets.pop(out_net[inst], None)
        root = d.nets[R]
        root.terms = [t for t in root.terms
                      if not (t[0] in member_set and t[1] in cfg.in_pins)]
        root.terms += even_sinks
        if even_port_nets:                       # C1: port net name wins the merge
            keep = even_port_nets[0]
            del d.nets[R]
            root.name = keep
            d.nets[keep] = root
            for other in even_port_nets[1:]:     # rare multi-port merge: fix PINS refs
                d.mid = d.mid.replace(f"+ NET {other}", f"+ NET {keep}")
                stats.pin_net_rewrites += 1
            R = keep
        if odd_sinks:
            iname = f"{cfg.new_inst_prefix}{counter}"
            nname = odd_port_nets[0] if odd_port_nets else f"{cfg.new_net_prefix}{counter}"
            counter += 1
            d.components[iname] = Component(iname, cfg.new_cell, "+ SOURCE TIMING")
            d.nets[nname] = Net(nname,
                                [(iname, cfg.new_cell_out_pin)] + odd_sinks, "")
            for other in odd_port_nets[1:]:
                d.mid = d.mid.replace(f"+ NET {other}", f"+ NET {nname}")
                stats.pin_net_rewrites += 1
            d.nets[R].terms.append((iname, cfg.new_cell_in_pin))
            stats.inserted.append(iname)
    return stats
```

Implementer notes:
- Root iteration over `list(d.nets)` is required because rebuild mutates `d.nets`.
  New nets (fresh `DBT_N_*` names or reused port-net names) have no BI in-pin
  loads in the `bi_loads` index built at start, so they can never be roots.
- Multi-output BI cells cannot occur (buffers/inverters are 1-in-1-out by
  definition of the classification config).
- The C1 rename (`root.name = keep`) relies on the port net having been popped
  already (it was a member out_net) — assert `keep not in d.nets` before
  re-inserting if paranoid.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_core.py -q`
Expected: 9 passed

- [ ] **Step 5: Full suite**

Run: `python3 -m pytest -q`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add dbt/core.py tests/test_core.py dbt/cells.py tests/test_cells.py
git commit -m "feat: deleteBufferTree core (per-tree rebuild, parity groups, single-INV skip)"
```

---

### Task 5: CLI

**Files:**
- Create: `dbt/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `python3 -m dbt.cli --input X.def --output Y.def --node asap7` → writes Y.def, prints one summary line `DBT: removed=N inserted=M trees=T skipped_single_inv=S` to stdout, exit 0.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import subprocess, sys

def test_cli_mini(tmp_path):
    out = tmp_path / "out.def"
    r = subprocess.run(
        [sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
         "--output", str(out), "--node", "asap7"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "removed=9" in r.stdout and "inserted=3" in r.stdout
    assert out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -q`
Expected: FAIL

- [ ] **Step 3: Implement dbt/cli.py**

```python
# dbt/cli.py
import argparse
from .def_parser import parse_def
from .def_writer import write_def
from .cells import get_config
from .core import run_dbt

def main():
    ap = argparse.ArgumentParser(description="Standalone DEF-in/DEF-out deleteBufferTree")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--node", required=True, choices=["asap7", "tsmcn7"])
    a = ap.parse_args()
    d = parse_def(a.input)
    stats = run_dbt(d, get_config(a.node))
    write_def(d, a.output)
    print(f"DBT: removed={len(stats.removed)} inserted={len(stats.inserted)} "
          f"trees={stats.trees} skipped_single_inv={stats.skipped_single_inv}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli.py -q`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add dbt/cli.py tests/test_cli.py
git commit -m "feat: CLI entry point"
```

---

### Task 6: Structural comparator

**Files:**
- Create: `compare/compare_dbt.py`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: three DEF paths (pre, candidate, golden) + node.
- Produces: `compare(pre, cand, gold, cfg) -> Report`; CLI `python3 compare/compare_dbt.py --pre P --ours O --golden G --node asap7` prints a report and exits 0 iff PERFECT.
- `Report` fields: `removed_only_ours: set`, `removed_only_gold: set`, `sink_mismatches: list`, `insert_count_ours: int`, `insert_count_gold: int`, `perfect: bool`.

Comparator semantics (name-agnostic on NEW insts/nets):

1. `removed(X) = pre.components − X.components` (by name). Diff ours vs golden directly (old names are stable).
2. New insts: `X.components − pre.components`. Signature of a new inst i in design X: `sig(i) = (input_root_net_name, frozenset(sinks))` where `input_root_net` = the net containing term `(i, in_pin)` (root nets keep pre names in both designs) and `sinks` = terms on i's output net except i itself. Compare multisets of signatures.
3. Sink-level map: for every term `(comp, pin)` in the candidate where comp survives (or PIN term): resolve `source(term)` = walk: term's net → if driven by a NEW inverter, `(root_of_that_inverter, 1)`; if an ORIGINAL net, `(net_name, 0)`. Same for golden. Every term must resolve identically. (Original surviving inverters keep their nets — parity handled by net identity.)
4. `perfect = no removed diff ∧ signatures equal ∧ no sink mismatches`.

- [ ] **Step 1: Write the failing test — comparator must call our own mini output PERFECT against a hand-built golden with different new-inst names**

```python
# tests/test_compare.py
import subprocess, sys
from dbt.def_parser import parse_def
from dbt.cells import get_config
from compare.compare_dbt import compare

def test_self_perfect(tmp_path):
    out = tmp_path / "ours.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
                    "--output", str(out), "--node", "asap7"], check=True)
    # golden = same output but new insts/nets renamed like Innovus would
    text = out.read_text().replace("DBT_", "FE_DBTC").replace("FE_DBTCN_", "FE_OFN")
    gold = tmp_path / "gold.def"
    gold.write_text(text)
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert rep.perfect, (rep.removed_only_ours, rep.removed_only_gold,
                         rep.sink_mismatches[:5])

def test_detects_wrong_removal(tmp_path):
    out = tmp_path / "ours.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
                    "--output", str(out), "--node", "asap7"], check=True)
    # golden that (wrongly, per our tool) also kept U_INVS deleted: simulate by
    # removing U_INVS line from a copy of ours
    lines = [l for l in out.read_text().splitlines(True) if "U_INVS" not in l]
    gold = tmp_path / "gold.def"
    gold.write_text("".join(lines))
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert not rep.perfect
    assert "U_INVS" in rep.removed_only_gold

def test_detects_wrong_new_cell(tmp_path):        # review finding M2.1
    out = tmp_path / "ours.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
                    "--output", str(out), "--node", "asap7"], check=True)
    bad = tmp_path / "bad.def"
    bad.write_text(out.read_text().replace(
        "DBT_0 INVxp67_ASAP7_75t_SL", "DBT_0 BUFx2_ASAP7_75t_R"))
    rep = compare("tests/fixtures/mini.def", str(bad), str(out), get_config("asap7"))
    assert not rep.perfect
    assert any(e[1] == "BAD_NEW_CELL" for e in rep.integrity_errors)

def test_detects_swapped_sink_partition(tmp_path):   # Codex #2: same roots, wrong grouping
    # build ours normally, then fabricate a golden where one odd sink moved from
    # the mixed tree's new inverter onto the parallel-merge tree's new inverter
    out = tmp_path / "ours.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
                    "--output", str(out), "--node", "asap7"], check=True)
    d = parse_def(str(out))
    inv0, inv1 = [n for n in d.nets.values()
                  if any(c.startswith("DBT_") for c, _ in n.terms) and n.name != "netOB"][:2]
    moved = [t for t in inv0.terms if not t[0].startswith("DBT_")][0]
    inv0.terms.remove(moved); inv1.terms.append(moved)
    from dbt.def_writer import write_def
    gold = tmp_path / "gold.def"; write_def(d, str(gold))
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert not rep.perfect      # sink map and sig must both flag this

def test_reused_old_net_name_is_still_perfect(tmp_path):   # Codex #6 / Innovus behavior
    # golden variant: rename a new inverter's fresh DBT_N_* output net to an OLD
    # pre-DEF net name that the rebuild deleted (Innovus does exactly this)
    out = tmp_path / "ours.def"
    subprocess.run([sys.executable, "-m", "dbt.cli", "--input", "tests/fixtures/mini.def",
                    "--output", str(out), "--node", "asap7"], check=True)
    text = out.read_text().replace("DBT_", "FE_DBTC").replace("FE_DBTCN_0", "netY")
    gold = tmp_path / "gold.def"; gold.write_text(text)
    rep = compare("tests/fixtures/mini.def", str(out), str(gold), get_config("asap7"))
    assert rep.perfect, rep.sink_mismatches[:5]
```

(`FE_DBTCN_0` = what `DBT_N_0` becomes after the first replace; `netY` was the
mixed tree's deleted inverter-output net in pre — exactly Innovus's reuse
pattern. If the mixed tree's new net isn't index 0, adjust to the actual name —
the tests are the contract.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_compare.py -q`
Expected: FAIL (`ModuleNotFoundError: compare.compare_dbt`)

- [ ] **Step 3: Implement compare/compare_dbt.py**

```python
# compare/compare_dbt.py
import argparse, sys, os
from dataclasses import dataclass, field
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dbt.def_parser import parse_def
from dbt.cells import get_config
from collections import Counter

@dataclass
class Report:
    removed_only_ours: set = field(default_factory=set)
    removed_only_gold: set = field(default_factory=set)
    sig_only_ours: list = field(default_factory=list)
    sig_only_gold: list = field(default_factory=list)
    sink_mismatches: list = field(default_factory=list)
    integrity_errors: list = field(default_factory=list)
    insert_count_ours: int = 0
    insert_count_gold: int = 0
    perfect: bool = False

def _new_inst_index(pre, x, cfg):
    """new_inst -> (root_net, out_net). Also net -> owning new inst."""
    news = {n for n in x.components if n not in pre.components}
    in_of, out_of = {}, {}
    for net in x.nets.values():
        for comp, pin in net.terms:
            if comp in news:
                if pin in cfg.in_pins:
                    in_of[comp] = net.name
                elif pin in cfg.out_pins:
                    out_of[comp] = net.name
    return news, in_of, out_of

def _sink_map(pre, x, cfg):
    """(comp,pin) -> (source_root, parity) for every surviving/PIN sink term.
    Hardened per review M2: duplicate (comp,pin) on >1 net is an integrity error;
    every new inst must be exactly cfg.new_cell."""
    news, in_of, out_of = _new_inst_index(pre, x, cfg)
    owner = {onet: i for i, onet in out_of.items()}
    m, errors = {}, []
    for i in news:
        if x.components[i].cell != cfg.new_cell:
            errors.append(("BAD_NEW_CELL", i, x.components[i].cell))
    for net in x.nets.values():
        for comp, pin in net.terms:
            if comp in news:
                continue
            if net.name in owner:
                src = (in_of.get(owner[net.name], "?"), 1)
            else:
                src = (net.name, 0)
            if (comp, pin) in m and m[(comp, pin)] != src:
                errors.append(("DUP_TERM", (comp, pin), m[(comp, pin)], src))
            m[(comp, pin)] = src
    # PINS integrity: every port's '+ NET' must reference an existing net
    # that actually contains the ( PIN port ) term
    for port, netname in x.pin_nets.items():
        net = x.nets.get(netname)
        if net is None or ("PIN", port) not in net.terms:
            errors.append(("DANGLING_PIN", port, netname))
    return m, news, in_of, out_of, errors

def _sig(x, news, in_of, out_of):
    """new-inst signature per plan semantics: (root net, frozenset of sinks)."""
    sigs = Counter()
    for i in news:
        onet = x.nets.get(out_of.get(i, ""), None)
        sinks = frozenset(t for t in (onet.terms if onet else []) if t[0] != i)
        sigs[(in_of.get(i, "?"), sinks)] += 1
    return sigs

def compare(pre_p, ours_p, gold_p, cfg) -> Report:
    pre, ours, gold = parse_def(pre_p), parse_def(ours_p), parse_def(gold_p)
    r = Report()
    rem_o = set(pre.components) - set(ours.components)
    rem_g = set(pre.components) - set(gold.components)
    r.removed_only_ours = rem_o - rem_g
    r.removed_only_gold = rem_g - rem_o
    mo, news_o, in_o, out_o, err_o = _sink_map(pre, ours, cfg)
    mg, news_g, in_g, out_g, err_g = _sink_map(pre, gold, cfg)
    r.integrity_errors = [("ours",) + e for e in err_o] + [("gold",) + e for e in err_g]
    r.insert_count_ours, r.insert_count_gold = len(news_o), len(news_g)
    sig_o, sig_g = _sig(ours, news_o, in_o, out_o), _sig(gold, news_g, in_g, out_g)
    r.sig_only_ours = sorted((sig_o - sig_g).elements())
    r.sig_only_gold = sorted((sig_g - sig_o).elements())
    for term in set(mo) | set(mg):
        a, b = mo.get(term), mg.get(term)
        if a != b:
            r.sink_mismatches.append((term, a, b))
    # surviving comps must keep their cell (resize would be a rule violation)
    for name in set(pre.components) & set(ours.components) & set(gold.components):
        co, cg = ours.components[name].cell, gold.components[name].cell
        if co != cg:
            r.integrity_errors.append(("CELL_DIFF", name, co, cg))
    r.perfect = not (r.removed_only_ours or r.removed_only_gold
                     or r.sig_only_ours or r.sig_only_gold
                     or r.sink_mismatches or r.integrity_errors)
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", required=True)
    ap.add_argument("--ours", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--dump", help="write full mismatch lists to this file")
    a = ap.parse_args()
    r = compare(a.pre, a.ours, a.golden, get_config(a.node))
    print(f"removed: ours-only={len(r.removed_only_ours)} gold-only={len(r.removed_only_gold)}")
    print(f"inserted: ours={r.insert_count_ours} gold={r.insert_count_gold}")
    print(f"insert-sig diff: ours-only={len(r.sig_only_ours)} gold-only={len(r.sig_only_gold)}")
    print(f"sink mismatches: {len(r.sink_mismatches)}")
    print(f"integrity errors: {len(r.integrity_errors)}")
    for e in r.integrity_errors[:10]:
        print(f"  {e}")
    for t, x, y in r.sink_mismatches[:10]:
        print(f"  {t}: ours={x} gold={y}")
    if a.dump:
        with open(a.dump, "w") as f:
            for s in sorted(r.removed_only_ours): f.write(f"REMOVED_ONLY_OURS {s}\n")
            for s in sorted(r.removed_only_gold): f.write(f"REMOVED_ONLY_GOLD {s}\n")
            for t, x, y in r.sink_mismatches: f.write(f"SINK {t} ours={x} gold={y}\n")
    print("VERDICT:", "PERFECT" if r.perfect else "MISMATCH")
    sys.exit(0 if r.perfect else 1)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_compare.py -q`
Expected: 5 passed

- [ ] **Step 5: Comparator sanity — golden vs golden must be PERFECT**

Run:
```bash
G=/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_ariane/result/ariane
python3 compare/compare_dbt.py --pre $G/ariane_pre_deleteBufferTree.def \
  --ours $G/ariane_post_deleteBufferTree_withUnplaced.def \
  --golden $G/ariane_post_deleteBufferTree_withUnplaced.def --node asap7
```
Expected: `VERDICT: PERFECT` (also implicitly checks: removed 9536 both sides, inserted 1703 both sides — printed counts must show `inserted: ours=1703 gold=1703`).

- [ ] **Step 6: Commit**

```bash
git add compare/compare_dbt.py tests/test_compare.py
git commit -m "feat: name-agnostic structural comparator"
```

---

### Task 7: asap7 golden run + mismatch triage loop

**Files:**
- Create: `out/` (gitignored), `docs/2026-07-06-match-report.md`
- Modify: whatever the evidence demands (`dbt/core.py`, `dbt/cells.py`) — every change driven by a named mismatch class, committed separately.

- [ ] **Step 1: Run the tool on the asap7 golden input**

```bash
mkdir -p out
G=/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_ariane/result/ariane
time python3 -m dbt.cli --input $G/ariane_pre_deleteBufferTree.def \
  --output out/asap7_ours.def --node asap7
```
Expected: summary line; removed should be ~9,536 and inserted ~1,703 (bounds sanity: removed within 9,536±200, inserted within 1,703±100 — if wildly off, a classification or graph bug exists; go back to Task 4 with a concrete failing case distilled into a new mini-fixture test).

- [ ] **Step 2: Compare against golden**

```bash
python3 compare/compare_dbt.py --pre $G/ariane_pre_deleteBufferTree.def \
  --ours out/asap7_ours.def \
  --golden $G/ariane_post_deleteBufferTree_withUnplaced.def \
  --node asap7 --dump out/asap7_mismatches.txt
```

- [ ] **Step 3: Triage loop (repeat until PERFECT or residuals are evidence-classified)**

For each mismatch class in `out/asap7_mismatches.txt`:
1. Pick one concrete instance; extract its full pre-DEF local topology (root net, members, sinks) with a throwaway script.
2. Determine which side is "wrong" relative to the empirical rule; if Innovus behavior reveals a NEW rule facet (e.g. odd-group split at high fanout, special handling of port sinks, SOURCE-prop cells), write it down in `docs/2026-07-06-match-report.md`.
3. Distill the topology into a new mini-fixture test in `tests/test_core.py` (failing), fix `core.py`/`cells.py`, all tests green, commit with the mismatch class named in the message.
4. Re-run Steps 1–2.

**Do not declare victory on counts** (review finding M1): a single misclassified
cell family can hide inside ±200 count bounds — only `VERDICT: PERFECT` from the
comparator counts as a match. Counts are a smoke test, nothing more.

Exit criteria: `VERDICT: PERFECT`, or a report section "Residual classes" where every remaining mismatch is (a) counted, (b) explained with a concrete example, (c) attributed to information a DEF-only tool cannot have (e.g. timing-arc SPECIAL data from lib). Known candidates from prior analysis: the 32 "other" cases, the 3 pre-existing INVxp67_SL instances.

- [ ] **Step 4: Commit the report**

```bash
git add docs/2026-07-06-match-report.md
git commit -m "docs: asap7 match report (verdict + residual classes)"
```

---

### Task 8: tsmcn7 cross-node validation

**Files:**
- Modify: `dbt/cells.py` (only if evidence demands), `docs/2026-07-06-match-report.md`
- **NDA guard: outputs stay in `out/` (gitignored) or on /cedar; only counts go into the report.**

- [ ] **Step 1: Run + compare**

```bash
G7=/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_tsmcn7_ariane/result/ariane
time python3 -m dbt.cli --input $G7/ariane_pre_deleteBufferTree.def \
  --output out/tsmcn7_ours.def --node tsmcn7
python3 compare/compare_dbt.py --pre $G7/ariane_pre_deleteBufferTree.def \
  --ours out/tsmcn7_ours.def \
  --golden $G7/ariane_post_deleteBufferTree_withUnplaced.def \
  --node tsmcn7 --dump out/tsmcn7_mismatches.txt
```
Expected first pass: likely MISMATCH concentrated in cell-classification (TSMC family zoo: SKR/skew cells, DEL, CKB variants). Triage identically to Task 7 Step 3. The classification ground truth for tsmcn7 is derivable from the golden itself: any cell family 100%-removed by Innovus but classified None by us → add pattern; family kept by Innovus but removed by us → narrow pattern.

- [ ] **Step 2: Update report with tsmcn7 verdict + counts, commit**

```bash
git add docs/2026-07-06-match-report.md dbt/cells.py tests/test_cells.py
git commit -m "feat: tsmcn7 config validated against golden; cross-node match report"
```

---

### Task 9: Determinism + performance guard

**Files:**
- Test: `tests/test_determinism.py`

- [ ] **Step 1: Write test — two runs on mini.def byte-identical**

```python
# tests/test_determinism.py
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
```

- [ ] **Step 2: Run, expect PASS (dict ordering is insertion-ordered; no randomness). If FAIL, find the nondeterminism (sets in iteration order?) and fix.**

Run: `python3 -m pytest tests/test_determinism.py -q`

- [ ] **Step 3: Performance check on the real DEF: the Task 7 `time` must be < 120 s (Innovus itself: 5 s for the delete; ours includes parse+write of 33 MB). If slower, profile before optimizing.**

- [ ] **Step 4: Commit**

```bash
git add tests/test_determinism.py
git commit -m "test: determinism guard"
```

---

### Task 10: Golden generation for additional testcases (both nodes)

**Files:**
- Create: `scripts/gen_golden.sh` (committed), goldens land on /cedar (NOT in repo)

**Purpose:** one design per node cannot prove generality. Generate Innovus
pre/post golden pairs for the remaining corpus with the exact recipe already
validated on ariane, then validate the tool against every design in Task 11.

**Design lists (inputs verified to exist at plan time for ariane; Step 1 verifies the rest):**
- asap7 (`~/asap7/ICCAD25_testcases/<d>/`): `aes`, `pci_bridge32`, `netcard_fast`, `NV_NVDLA_partition_c`, `mempool_tile_wrap`, `ChipTop` — the six remaining designs the `complete_place_opt_iccad25` baseline ran.
- tsmcn7 (`~/routing-benchmarks/tsmcn7/<d>/original/`): `ac97_top`, `aes`, `aes_cipher_top`, `des`, `mempool_tile_wrap`, `NV_NVDLA_partition_c`, `pci_bridge32` — the seven remaining benchmark designs.

**Golden layout convention (same as ariane):** `/cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_<node>_batch/<design>/` containing `<design>_pre_deleteBufferTree.def`, `<design>_post_deleteBufferTree_withUnplaced.def`, `deleteBufferTree.log`, `innovus_*.log{,v}`. **No `.enc` for batch designs** (disk); the DEF pair is sufficient for validation. tsmcn7 goldens are NDA and never leave /cedar.

- [ ] **Step 1: Input preflight — record an availability matrix**

For each design, check the input files exist and note the netlist filename
(asap7 designs vary: ariane needed `ariane_fixed.v`; others may ship `<d>.v`
only — take `<d>_fixed.v` if present else `<d>.v`):

```bash
for d in aes pci_bridge32 netcard_fast NV_NVDLA_partition_c mempool_tile_wrap ChipTop; do
  p=~/asap7/ICCAD25_testcases/$d
  ls $p/$d.def $p/${d}_fixed.v 2>/dev/null || ls $p/$d.def $p/$d.v 2>/dev/null \
    || echo "MISSING: $d"
done
for d in ac97_top aes aes_cipher_top des mempool_tile_wrap NV_NVDLA_partition_c pci_bridge32; do
  p=~/routing-benchmarks/tsmcn7/$d/original
  ls $p/$d.def $p/$d.v $p/$d.sdc >/dev/null 2>&1 || echo "MISSING: $d"
done
```
Designs with missing inputs are dropped from the matrix WITH the evidence noted
in the match report — no silent skips.

- [ ] **Step 2: Write `scripts/gen_golden.sh`**

Parameterized wrapper generating a per-design TCL (same shape as the validated
`rerun_enc_defout.tcl`, minus saveDesign) and launching headless Innovus. Node
specifics come from the same two recipes already proven on ariane:
- asap7: env of `complete_place_opt_iccad25` (LIB/LEF/QRC globs, MMMC `fast`
  view, 4×globalNetConnect), netlist per Step 1, `defIn <d>.def`.
- tsmcn7: `tsmcn7_flow/flow/place.tcl` enablement recipe (tech_n7 + tcbn07 +
  mem LEF/NLDM globs, QRC, `setDesignMode -process 7`, VDDM globalNetConnect),
  SDC from the testcase dir.

Body per design: `defOut -floorplan -netlist -routing` pre → `deleteBufferTree
-verbose` (redirect to `deleteBufferTree.log`) → `defOut -floorplan -netlist
-routing -unplaced` post. Sequential execution, `--maxpar 2` at most (each
session takes a license); expect 10–40 min/design (ChipTop ~427k cells is the
long pole). Log-check each run per the monitor checklist (real-error grep)
before accepting its golden.

- [ ] **Step 3: Generate goldens, spot-verify each**

For every completed design: pre COMPONENTS == netlist inst count, post
COMPONENTS == pre − removed + inserted (from the tool log "Buffer/Inverters
difference"), zero non-benign errors. Record per-design removed/inserted counts
in the match report table.

- [ ] **Step 4: Commit the harness (scripts only)**

```bash
git add scripts/gen_golden.sh
git commit -m "feat: golden generation harness for multi-design corpus"
```

---

### Task 11: Full-corpus validation matrix

**Files:**
- Modify: `docs/2026-07-06-match-report.md` (final matrix), `dbt/cells.py`/`local/tsmcn7.json` only on comparator evidence

- [ ] **Step 1: Run tool + comparator over the whole matrix**

```bash
for g in /cedar/cedar_coe/ece-limsk/hhsiao30/deleteBufferTree_asap7_batch/*/; do
  d=$(basename $g)
  python3 -m dbt.cli --input $g/${d}_pre_deleteBufferTree.def \
    --output out/asap7_${d}.def --node asap7
  python3 compare/compare_dbt.py --pre $g/${d}_pre_deleteBufferTree.def \
    --ours out/asap7_${d}.def \
    --golden $g/${d}_post_deleteBufferTree_withUnplaced.def \
    --node asap7 --dump out/asap7_${d}_mm.txt
done
# same loop for tsmcn7_batch with --node tsmcn7
```

- [ ] **Step 2: Triage any non-PERFECT design exactly per Task 7 Step 3** (new
topology ⇒ new mini-fixture test ⇒ fix ⇒ re-run whole matrix — a fix for one
design must not break another; the matrix reruns in minutes, Innovus is not
re-run).

- [ ] **Step 3: Final report table** — one row per (node, design): pre/post/removed/inserted counts, verdict, residual classes if any. Commit.

```bash
git add docs/2026-07-06-match-report.md
git commit -m "docs: full-corpus validation matrix (asap7 x7, tsmcn7 x8)"
```

## Self-Review (done at plan-writing time)

- Spec coverage: DEF-in ✓ (Task 2), DEF-out ✓ (Task 3), deleteBufferTree ✓ (Task 4), compare-vs-Innovus ✓ (Tasks 6–8). Gaps: none known; open behavioral questions are explicitly parked in Task 7/8 triage.
- Placeholders: triage loop is inherently evidence-driven (cannot pre-write the fix), but its *procedure* is fully specified with exit criteria.
- Type consistency: `NodeConfig` gains `new_cell_out_pin`/`new_cell_in_pin` in Task 4 — Task 1's test must be updated in the same commit (noted in Task 4 interface).
