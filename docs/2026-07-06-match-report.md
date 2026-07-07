# deleteBufferTree clone — Innovus match report (FINAL, 2026-07-07)

Tool: `dbt` (this repo), DEF-in/DEF-out. Golden: Innovus v25.11-s102_1 standalone
`deleteBufferTree -verbose` on pre-CTS place_opt designs; goldens exported
`defOut -floorplan -netlist -routing -unplaced` (both pre and post — pre without
-unplaced breaks the diff basis on netlist/DEF-mismatched testcases; learned on ChipTop).
Match criterion: structural equivalence — exact removed-instance set, (root, sink-set)
signatures for inserted inverters, per-sink (source, parity) map, integrity checks
(new-cell identity, duplicate terms, PINS `+ NET` validity, surviving-cell identity).

## Full-corpus validation matrix

| node | design | pre insts | verdict |
|---|---|---|---|
| asap7  | ariane               | 105,730 | **PERFECT** |
| asap7  | aes                  |  ~29k   | **PERFECT** |
| asap7  | pci_bridge32         |  ~46k   | **PERFECT** |
| asap7  | netcard_fast         | ~316k   | **PERFECT** |
| asap7  | NV_NVDLA_partition_c | ~185k   | **PERFECT** |
| asap7  | mempool_tile_wrap    | ~300k   | **PERFECT** |
| asap7  | ChipTop              | 438,554 | RESIDUAL (hierarchical netlist — see below) |
| tsmcn7 | ariane               | 126,039 | **PERFECT** |
| tsmcn7 | ac97_top             |  ~12k   | **PERFECT** |
| tsmcn7 | aes                  |  ~13k   | **PERFECT** |
| tsmcn7 | aes_cipher_top       |  ~21k   | **PERFECT** |
| tsmcn7 | des                  |   ~5k   | **PERFECT** |
| tsmcn7 | mempool_tile_wrap    | ~110k   | **PERFECT** |
| tsmcn7 | NV_NVDLA_partition_c | ~226k   | **PERFECT** |
| tsmcn7 | pci_bridge32         |  ~30k   | **PERFECT** |

**14 / 15 PERFECT.** Tool runtime seconds per design (vs ~10-40 min Innovus session).

## The verified rule (final form)

Per root net (no valid buffer/inverter driver), collect the maximal BI tree, then:
1. **Clock exemption (tree-level):** if the root net or any member output net carries a
   clock-pin sink (CLK / CP; config per node), OR lies on the SDC clock cone
   (forward closure from create_clock ports through combinational cells, stopping at
   sequential clock pins; `--sdc` option), the whole tree is untouched — including
   its data branches (NVDLA: 17/17 CLK trees fully kept, 5 of them mixed clock+data).
2. **Single-inverter skip:** a one-member inverter tree is never touched (with or
   without sinks).
3. Otherwise rebuild: delete every member; even-parity sinks reattach to the root
   net; ALL odd-parity sinks share ONE new minimal low-Vt inverter (unplaced,
   `+ SOURCE TIMING`). Port-net names always survive the merge.
4. Valid BI = classified cell with exactly one recognized input and output net;
   anything else acts as ordinary logic (guards against pin-role gaps, e.g. the
   TSMC clock-NAND2 family that shares the inverter prefix).

## tsmcn7 classification corrections (evidence-derived, NDA config local-only)

Beyond the ariane round: skew buffers (BUFFSKRD/BUFFSKFD), INVSKFD, INVPADD,
DCCKNTWBD, **DCCKBD** (ac97: delay clock buffers removed by Innovus), **CKNTWAD**
(mempool: TWA variant), and the `CKND\d+BWP` anchoring fix (clock NAND2 false
positive, 6,336 instances shielded by the valid-BI guard).

## ChipTop residual class (documented limitation)

ChipTop is the ONLY hierarchical netlist in the corpus (383 modules; all other
designs are flat single-module). Result vs golden after basis fix: 0 under-removals,
2,606 over-removals (0.6% of 438,554; HB1xp67 x2,127 + small INV set) + cascaded
sink diffs. Evidence that hierarchy drives the divergence:
- All 12 flat designs match exactly on both nodes with one rule set.
- Innovus keep-patterns concentrate at module boundaries: buffers driving module
  output-port nets (reset_sync io_q), depth-0 inverters on module input-port nets
  (bootrom auto_in_*), fully-dangling buffer islands (undriven diplomacy stubs),
  and 163 partial trees — impossible under the flat-verified atomic-tree rule,
  consistent with per-module-scope processing of a hierarchical DB.
- Systematic feature scans (root driver class, sink pin class, SRAM/ASYNC adjacency,
  fanout, name-scope proxies) each fail to linearly separate keeps from removals in
  the flat view — the separating information (module port boundaries) is not in DEF.
Innovus itself flags this testcase: its DEF references instances absent from the
netlist (IMPDF-138, previous-generation FE_DBTC cells), 125k import warnings.
Conclusion: replicating hierarchical deleteBufferTree needs the hierarchical
netlist (future work: optional --hier-verilog input); a flat-DEF tool is complete
for flat netlists, which this corpus's other 12 designs prove cross-node.

## Execution deviations from plan
- Plan's odd-port fixture used a single-INV tree (skip case); replaced with 2-member tree.
- PG pins (USE POWER/GROUND) excluded from PINS-integrity (reference SPECIALNETS).
- Pre-DEF golden exports also need `-unplaced` (ChipTop basis lesson) — gen_golden.sh fixed.
- Dangling-buffer fixture expectation (delete) matches flat-design behavior; ChipTop's
  kept dangling islands are part of the hierarchical residual class.
