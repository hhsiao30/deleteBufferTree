# Innovus deleteBufferTree 行為規則與演算法(中文參考)

> 本文件是 `dbt_tool` 的規則依據。每一條規則都經過「與 Innovus v25.11 golden 輸出結構等價比對」驗證:
> **正式語料 14/14 PERFECT**(asap7 六個設計 + tsmcn7 八個設計,全部 pre-CTS place_opt 階段、flat netlist)。
> 驗證方法與逐設計結果見 `2026-07-06-match-report.md`。

---

## 一、這個步驟在做什麼

- `deleteBufferTree` 是 Innovus `place_opt_design` 的**第一步**(在 global placement 之前自動執行,也可單獨呼叫)。
- 目的:synthesis / 前一輪最佳化留下的 buffer 樹是**舊 timing 環境的產物**,留著會誤導初始 placement。
  所以把「對邏輯零貢獻的 cell(buffer)」全部刪掉,把「反相(inverter)」壓到邏輯最小數量,
  之後的 placement + optDesign 會在新位置重建需要的 buffering。
- **不變量(邏輯合約):每一個 sink pin 收到的訊號極性,刪除前後完全相同。**
  至於用哪顆 cell、幾顆 cell 來兌現這個合約,工具一律重新來過,並刻意選最便宜的答案。

## 二、名詞定義

| 名詞 | 定義 |
|---|---|
| **BI cell** | buffer 或 inverter。判定靠 cell name pattern(見第三節),不靠 timing library。 |
| **有效 BI** | 被分類為 BI **且**在 netlist 上找得到「恰好一個輸入 net + 一個輸出 net」的 instance。缺任一者(pin 角色不符,例如 TSMC 的 clock-NAND2 家族和 inverter 共用名稱前綴)一律當**普通邏輯**處理,絕不參與樹偵測。 |
| **root net(樹根)** | 一條 net,上面掛著至少一顆有效 BI 的**輸入**,而且這條 net **不是**任何有效 BI 的輸出。也就是:樹的起點是邏輯 gate 輸出、flop 輸出、或 top-level port。 |
| **樹(tree)** | 從 root net 出發,經由有效 BI「輸入→輸出」關係可連續到達的所有 BI instance 集合。碰到非 BI cell 就停(那是 sink)。**一條 root net 恰好對應一棵樹**——同一 root 上的多顆平行 BI 屬於同一棵樹。 |
| **成員(member)** | 樹裡的 BI instance。 |
| **sink** | 成員輸出 net 上、**不屬於**本樹成員的任何接腳:邏輯 cell 的輸入 pin、flop/macro 的 pin、或 top-level port(DEF 的 `( PIN name )` term)。注意:root net 上原本就直接掛著的非 BI 負載**不是** sink,它們不動。 |
| **極性(parity)** | 從 root 走到該 sink 沿途經過的 inverter 數目,取奇偶。偶=與 root 同相;奇=反相。buffer 不改變極性。 |

## 三、cell 分類(每個製程節點一份 config)

- **buffer 家族**(asap7 例):`BUFx*`、`HB<數字>*`(hold buffer)、`CKBUF*`。
  tsmcn7:一般 buffer、clock buffer、skew buffer(SKR/SKF)、delay-clock buffer(DCCKB)等家族
  (完整清單含 NDA cell 名,放在未提交的 `local/tsmcn7.json`)。
- **inverter 家族**(asap7 例):`INVx*`、`CKINV*`。
  tsmcn7:一般 inverter、clock inverter、TWA/TWB 變體、skew inverter、pad inverter、DCCKNTWB 等。
- **兩個實證教訓:**
  1. **名稱前綴會誤傷**:tsmcn7 的 clock-NAND2 家族(`CKND2D*`,pin 是 A1/A2)和 clock inverter
     (`CKND<驅動數字>`,pin 是 I)共用 `CKND` 前綴。pattern 必須錨定(如 `CKND\d+BWP`),
     而「有效 BI」防護是第二道保險——pin 對不上的 cell 自動退回普通邏輯,不會誤刪
     (實測擋下 6,336 顆;tsmcn7 ariane)。
  2. **分類的最終裁判是 golden diff**,不是文件(修正 2026-07-07:早前寫「DCCKND 不刪」
     是空集合命題——全語料 DCCKND/DEL instance 數為 0,從未被驗證)。
  3. **通用模式(推薦):`--lib` 直讀 Liberty** —— cell 是否 buffer/inverter 由 `function`
     屬性判定(`I` vs `!I`),pin 方向、clock pin、面積全部來自 lib,無名字 pattern、無節點寫死。
     14/14 全語料驗證與 pattern 模式等價(兩節點皆 PERFECT)。陷阱:regex 必須錨定行首,
     否則 `power_down_function` 會誤中。pin 盤點:`python3 -m dbt.liberty --libs <globs> --out pins.csv`。
- **替換用 inverter**(重建時插入的補償 cell)是**每節點固定一顆**:
  asap7 = `INVxp67_ASAP7_75t_SL`(低 Vt、小驅動);tsmcn7 = 最小驅動的 D1 ULVT inverter。
  不會沿用被刪 inverter 的型號——**sizing 資訊刻意歸零**,交給後續 optDesign 重選。

## 四、演算法主流程(對每一條 root net,獨立結算)

```
對每條 root net R:
  1. BFS 收集樹成員(記錄每個成員的極性深度)
  2. 單顆 inverter 檢查 → 樹只有一顆 INV(不論有無 sink)則跳過
  3. 豁免檢查(見第五節)→ 命中則整棵跳過
     (2、3 順序只影響統計歸類:落在 clock 錐上的單顆 INV 計入 skipped_single_inv
      而非 skipped_clock;對輸出 DEF 無影響)
  4. 重建:
     a. 收集全部 sink,按極性分成「偶群」「奇群」
     b. 刪除全部成員 instance,刪除全部成員輸出 net
     c. 偶群 sink → 直接改接到 R(零成本)
     d. 奇群 sink 非空 → 建一顆新的替換 inverter:
        輸入接 R,輸出接一條 net,奇群全部掛上去
        (整棵樹的奇群共用「一顆」inverter——不管它們原本分屬幾顆不同的 inverter)
     e. net 命名規則(見第六節)
```

- **帳目性質:** 每棵樹最多插 1 顆、刪 ≥1 顆,所以**永遠不虧**;唯一打平的情況(單顆 INV,刪1插1)
  直接跳過不做。這等價於「會賺才重建」。
- **合併效應:** 平行的 inverter 分身(前一輪 opt 做 fanout 分攤留下的 clone)會被併成一顆
  (asap7 ariane 實測:最多 12 顆併 1 顆)。
- **「假 1:1 替換」現象:** 若某成員剛好位於樹根第一層、其輸出 net 又被沿用,看起來像
  「單顆 INV 原地換成新 inverter」。它其實仍是整棵重建的一環——它的兄弟或下游必然同時被刪。
  孤立單顆 INV 被替換的案例:**零**。

## 五、豁免規則(命中任一 → 整棵樹原封不動)

1. **Clock 豁免(樹級,preCTS 就會生效):** 滿足任一即豁免——
   - root net 或任何成員輸出 net 上,掛著 **clock pin** sink(asap7:`CLK`;tsmcn7:`CP`/`CLK`);
   - root net 或任何成員輸出 net 落在 **SDC clock 錐**上。
     clock 錐 = 從每個 `create_clock` 的 port net 出發,穿過組合邏輯 cell(clock gate 的
     AND、mux、buffer/inverter……)向前傳播;碰到時序元件(有 clock pin 的 cell)的 clock pin
     即終止;時序元件的 Q 端**不**延續(除非 SDC 另有 generated clock——本語料沒有)。
     **實作註:** 「組合 cell 的輸出」以 pin 名判定(config 的 out_pins ∪ {Y, Z, ZN});
     輸出腳名不在此集合的組合 cell(如加法器的 S/CO)會使 cone 在該處終止——本語料未觸發此邊界。
   - **重點:豁免是整棵樹,連 data 分支一起留。** asap7 NV_NVDLA_partition_c 實測:17 棵含 CLK sink 的樹全數保留,
     其中 5 棵是 clock+data 混合樹,data 分支也沒被拆。
   - 為什麼 preCTS 也會發生:CTS 前雖然沒有工具長出來的 clock tree,但 netlist 可能**自帶**
     clock gating / clock inverter chain(NVDLA 的 `CTS_ccl_*`),Innovus 的 timing graph
     一樣把它們標成 clock path。
2. **單顆 inverter 樹(有 sink):** 不動。由 flat 語料 14/14 + 1,908 個 QN 案例充分驗證。
3. **死 cell 與孤島(2026-07-07 探針定案,dbt_probes/dangling_probe + hier_probe P5/P6/P9):**
   - **有 driver、無 sink** 的 buffer「和單顆 inverter」→ **照刪**(死邏輯回收;單 INV 跳過規則
     不適用於無 sink 的情況——這推翻了本文件早前的假設,已修工具與測試)。
   - **完全孤島** → **整棵不碰**。定義(方向無關,刻意不依賴 pin 名判方向):
     root net 上除了樹成員自己的輸入腳之外**一無所有**(沒有任何其他 term),且全樹零 sink。
     教訓:第一版用「pin 名白名單判 driver 存在」實作,SRAM macro 輸出腳不在名單上,
     把 4 個設計從 PERFECT 打成 MISMATCH — 全語料回歸抓回來後改為此定義,14/14 恢復。
     (ChipTop 斷線 net 上的 157 顆「無 driver 但有 sink」保留屬於受損 testcase 行為,不納入 flat 規則。)
4. **Scan 不是豁免來源(探針驗證,2026-07-07):** scan path(QN→SI)上的 buffer 照刪,
   有無 `specifyScanChain` 定義結果相同(dbt_probes/scan_probe,兩版皆刪)。語料中 7/14 設計
   帶未串鏈 scan flop,均在 14/14 驗證內。scan 唯一注意事項是 defOut `-scanChain` 匯出旗標(第七節)。
5. **文件明載、本語料未觸發的豁免:** `-excNetFile` 排除名單、SDC `set_dont_touch`、
   timing arc 為 SPECIAL 的 cell、`-footprint` 限縮。使用這些功能的設計需另行驗證。

## 六、net 與 instance 的命名規則

- **root net 名字不變**(偶群 sink 併過來也是併到原名下)。
- **port net 名字必勝:** 任何被 PINS 段 `+ NET` 引用的 net 名字必須存活——
  - 偶群含 port sink:合併後的 net **改用該 port net 的名字**(root 原名消失);
  - 奇群含 port sink:新 inverter 的輸出 net **取該 port net 的名字**。
  - 依據:asap7 ariane golden 中 443 個 port 的 `+ NET` 引用零變動。違反此規則會產生「PINS 指向不存在 net」的非法 DEF。
  - **未驗證 corner:** 「多個 port net 在同一棵樹合併」(含 root 自身即為 port net)在全語料為 0 例;
    工具對此路徑的行為未經 golden 驗證(comparator 的 PINS 完整性檢查會在發生時抓出)。
- **新 instance:** Innovus 命名 `FE_DBTC*`(本工具用 `DBT_*`);
  DEF 屬性帶 `+ SOURCE TIMING`;**unplaced**(沒有座標——placement 是下一步的事)。
- **Innovus 會重用被刪 net 的舊名字**當新 inverter 的輸出 net 名(例如沿用原 sink 側 net 名)。
  比對時對「非 port 的新 net 名」必須 name-agnostic。

## 七、DEF 層面的注意事項(容易踩雷)

1. **unplaced cell 與 defOut:** 新插的 inverter 沒有座標。
   `defOut -floorplan ...` **預設不寫 unplaced cell**,要明加 `-unplaced`;
   裸 `defOut file.def` 反而會寫(但不含 NETS 段)。忘了 `-unplaced` 的後果:
   netlist 和 DEF 差一批 cell、NETS 段出現「有 load 沒 driver」的浮接 net。
2. unplaced component 在 DEF 裡**沒有 `UNPLACED` 關鍵字**——它長這樣:
   `- 名字 cell型號 + SOURCE TIMING ;`(整個 placement 欄位省略)。用 grep UNPLACED 找不到。
3. 執行後所有受影響 net 的 routing 會被清除(預設行為;`-preserveRoute` 只保未受影響 net)。
4. 比對兩次 deleteBufferTree 結果時,**pre DEF 也要用 `-unplaced` 匯出**——
   若輸入 testcase 的 netlist/DEF 不同步(有 cell 進 DB 後 unplaced),不加會讓 diff 基準殘缺。

## 八、工具輸入需求與 SDC 支援範圍(dbt_tool 專屬)

- **必要輸入:** DEF 必須含 `COMPONENTS` 與 `NETS` 段(缺任一直接報錯);`--node` 僅支援
  `asap7` / `tsmcn7`;**tsmcn7 需要未提交的 `local/tsmcn7.json`**(NDA config),
  缺檔會以明確錯誤訊息拒跑。
- **PINS 處理範圍:** 只追蹤 signal pin;`+ USE POWER/GROUND` 的 PG pin 指向 SPECIALNETS,
  排除在 port-net 命名與完整性檢查之外。
- **passthrough:** COMPONENTS/NETS 以外的段落(PINS、SPECIALNETS、TRACKS……)原樣保留,
  僅在 port-net 改名時改寫 PINS 的 `+ NET` 引用。
- **`--sdc` 支援範圍(重要——超出範圍會靜默漏 clock):**
  - 只解析 `create_clock ... [get_ports X]`;**`get_pins` 不支援**;
  - `[get_ports {a b}]` 大括號多 port **只取第一個**,其餘 clock 被漏掉;
  - `create_generated_clock` 不支援;指令必須在同一行;
  - **不給 `--sdc` 時 clock-錐豁免整個停用**,只剩「clock pin 直接掛在樹上」的豁免。
  - 多 clock 設計(如本語料的 ChipTop 型)務必給 `--sdc`,否則結果可能與 Innovus 不符而無警告。

## 九、已知適用範圍與極限

- **適用:pre-CTS、flat(單一 module)netlist。** 本語料 14 個 flat 設計跨兩個節點全數精確吻合。
- **階層式 netlist(多 module)不在保證範圍 —— 機制已破解(2026-07-07,三方獨立調查 + 因果探針):**
  真正的規則是 **uniquify 凍結**:netlist 非 unique 時(`init_design_uniquify=0` 預設),
  **被實例化 >1 次的 module 定義內部整體凍結不編輯**(改一份會改到所有 instance)。
  module **port 邊界本身不保護**(探針證明:跨 port 樹照刪,補償 inverter 甚至會打穿 port 插進 child)。
  ChipTop 全設計驗證:刪除側 0% 落在多實例 module、保留側 87% 落在其中;凍結+斷線+衍生規則
  合計解釋 93.7% 保留與 100% 刪除;殘餘 4% 溯源至該 testcase 受損 DB 的內部狀態,
  **原理上不可從 netlist+DEF 重現**(乾淨 DB 重建同拓撲會刪)→ ChipTop 維持排除。
  攤平對照:同一 netlist `saveNetlist -flat` 後重跑,Innovus 刪除集合變為階層版的嚴格超集
  (+2,421、反向 0),與本工具僅剩斷線 net 慣例差異——階層是因果主因,設計缺陷是殘餘。
  要覆蓋 ~96% 需一個新輸入(module 實例數表)+ 凍結系列規則(詳 match report 附錄)。
- **postCTS 未驗證:** clock 豁免規則是在 preCTS 語境驗的;CTS 之後 clock tree 存在,
  豁免的實際範圍需要另行 golden 驗證。
- **決定性:** 本工具同輸入必得 byte-identical 輸出(有測試守門)。Innovus 端實測可重現
  (asap7 ariane 兩次獨立 session,淨刪除量同為 −7,833)。

## 十、與 Innovus 的已知差異(刻意為之)

| 項目 | Innovus | 本工具 | 影響 |
|---|---|---|---|
| 新 instance 名 | `FE_DBTC<n>_<hint>` | `DBT_<n>` | 無(比對 name-agnostic)|
| 非 port 新 net 名 | 重用舊 net 名 | `DBT_N_<n>` | 無(同上)|
| 判定資訊來源 | timing graph + library | cell name pattern + pin 名 + SDC | flat 語料上零差異 |
| 受影響 net 的 routing | 清除 | 原樣保留(net props passthrough) | 無——本工具假設輸入為未繞線的 preCTS DEF |
