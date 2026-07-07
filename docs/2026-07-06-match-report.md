# deleteBufferTree clone — Innovus match report

Tool: `dbt` (this repo). Golden: Innovus v25.11-s102_1 standalone `deleteBufferTree -verbose`
on pre-CTS place_opt designs; goldens exported `defOut -floorplan -netlist -routing -unplaced`.
Match criterion: structural equivalence (exact removed-instance set, (root, sink-set)
signatures for inserted inverters, per-sink (source, parity) map, integrity checks:
new-cell identity, duplicate terms, PINS `+ NET` validity, surviving-cell identity).

## Single-design results (ariane)

| node | pre insts | removed | inserted | verdict | iterations |
|---|---|---|---|---|---|
| asap7  | 105,730 | 9,536 (exact set) | 1,703 (sig exact) | **PERFECT** | 1 (first run) |
| tsmcn7 | 126,039 | 14,526 (exact set) | 2,216 (sig exact) | **PERFECT** | 2 |

Tool runtime ~3 s per design; comparator ~8–16 s (vs Innovus session ~13 min incl. load).

## tsmcn7 iteration-2 corrections (all derived from golden evidence, NDA config local-only)

1. Missing buffer families: skew buffers (`BUFFSKRD`/`BUFFSKFD`, 1,756 instances,
   100% removed by Innovus) added as BUF.
2. Missing inverter families: `INVSKFD`, `INVPADD`, `DCCKNTWBD` (16/16 removed —
   the doc's "SPECIAL arc" exemption does NOT cover this delay-family inverter;
   plain `DCCKND` remains excluded and Innovus indeed keeps those).
3. False-positive pattern: `CKND` also matched `CKND2D*` / `CKND2TWBD*` — those are
   clock **NAND2** gates (pins A1/A2), not inverters. 6,336 instances were saved by
   the valid-BI degeneracy guard (Codex review finding #5) and correctly reclassified
   by anchoring the pattern to `CKND\d+BWP`.

## Execution deviations from plan

- Plan's odd-port fixture used a single-INV tree, which the (correct) single-INV skip
  rule leaves untouched; replaced with a two-member BUF+INV tree (plan synced).
- PG pins (`+ USE POWER/GROUND`) reference SPECIALNETS and are excluded from the
  PINS-integrity check (found by golden-vs-golden sanity; fixture extended).

## Rule (as implemented and verified)

Per root net (driven by no valid buffer/inverter): collect the maximal BI tree;
skip if it is a single inverter (with or without sinks — Innovus keeps even dangling
ones); otherwise delete every member, reattach even-parity sinks to the root net,
and give ALL odd-parity sinks one shared new minimal low-Vt inverter (unplaced,
`+ SOURCE TIMING`). Port-net names always survive (merged net or new-inverter output
net takes the port's `+ NET` name). Valid BI = classified cell with exactly one
recognized input and output net; anything else is treated as ordinary logic.

## Pending

- Full-corpus validation matrix (asap7 ×7, tsmcn7 ×8) — Tasks 10–11.
