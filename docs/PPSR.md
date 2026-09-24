# PPSR（自动定数）计算逻辑

> 本文只讲**一件事**：一张谱面的 PPSR 是怎么算出来的、这个数怎么被 pp 使用。
> 设计背景/历史决策见 [AUTO_DIFFICULTY.md](./AUTO_DIFFICULTY.md)，本文是它的「实现口径」版。

**一句话**：把 `.pez` 谱面解成音符序列 → 算 120 个描述「打起来有多难」的数值特征 → 用 GBDT
（200 棵小回归树）把它映射到定数刻度 → 做一次去收缩仿射 → 写进 `chart_auto_difficulty` → pp 计算时
按 `chart_id` 取这个值当定数（`sr`）。

---

## 0. 数据流总图

```
charts.file_path                      /uploads/charts/<sha>.pez
        │
        │ ① services/chartNotes.js     解包 + 复用游戏引擎（public/rulaios/js/chart.js）
        ▼
   音符流 notes[]                     {kind, t, end, ax, ay, ...}（绝对落点，已剔除 fake）
        │
        │ ② services/chartFeatures.js  G1–G10 指标 + 10s/5s 分段聚合
        ▼
   特征向量 x[120]                    （模型用其中 114 个，排除 meta_* 与 seg_peakTime/End）
        │
        │ ③ services/gbdt.js           200 棵回归树，学习「特征 → 旧定数表」
        │    services/difficultyModel.js
        ▼
   原始预测 p = GBDT(x)                刻度 = 旧定数表刻度
        │
        │ ④ 去收缩仿射 y = 1.0485·p − 0.8651   （系数用训练集折外预测拟合，不碰锚点）
        ▼
   PPSR                                 写进 chart_auto_difficulty.value，3 位小数
        │
        │ ⑤ services/difficulty.js     override > auto > charts.difficulty > chart_constants
        ▼
   pp 里的 sr  →  services/pp.js  BASE × sr^6 × acc × precision × error，前 100 条 0.95^i 衰减
```

落库与推理是**同一个函数**（`scripts/difficulty_calibration.js` 的 `fitFromPool()`：
`--predict` 与 `--apply` 共用），所以「报告里那一列预测值」和「库里那个值」永远一致。

---

## 1. 词汇表：PPSR vs 参考定数

| 名字 | 存哪 | 谁在用 | 说明 |
|---|---|---|---|
| **PPSR** | `chart_auto_difficulty.value`（人工修正优先：`chart_auto_difficulty_override`） | **pp 计算、谱面池/成绩/主页显示** | pp 实际用的定数，即 `routes/scores.js` 里记录的 `sr`，快照里还有 `difficulty_source` 标明来源 |
| 参考定数 | `charts.difficulty` | 只作对照显示（`ref_sr`），不参与 pp | 人工/定数表确认的值，即模型训练时的标签 |
| 社区定数表 | `chart_constants` | 只在 PPSR 与参考定数都拿不到时兜底 | 导入脚本写入 |

**段位谱例外**：段位池（`ranked.status='approved'`）引用的谱面**不进 pp**（`loadRankedChartIds()`
直接跳过），所以它们在成绩接口里 `ppsr = null`、`ppsr_source = 'ranked'`；但界面上仍用
`display_difficulty` 把它当普通谱面显示（段位页走 `resolveDisplayDifficulty()`：人工定数优先、
缺失时用自动值兜底，避免显示 0.00）。

---

## 2. 音符流抽取（流程①）— `services/chartNotes.js`（196 行）

- **解包**：`charts.file_path`（形如 `/uploads/charts/<sha>.pez`）在 `public/` 下解析成
  `extra.json` + `.json` 谱面；`EXTRACTOR_VERSION = 1`。
- **复用游戏引擎**：把前端 `public/rulaios/js/chart.js`（IIFE，无 DOM 依赖）加载进 `vm` 跑，
  保证「算法看到的音符」和「玩家实际打的音符」完全同源——包括判定线运动、RPE 事件时间轴。
- **绝对落点**（关键）：音符在**自己所在时刻**的判定线坐标系下的位置换算到世界坐标：

  ```
  rot = line.rotAt(t)                     // 该时刻判定线旋转角
  ax  = line.worldXAt(t) + note.x·cos(rot)
  ay  = -line.worldYAt(t) + note.x·sin(rot)
  ```

  之后所有横向指标（手型、位移、左右手分侧）都用 `ax`，而**不是** note.x —— 判定线会动，
  用 note.x 会算错横向间距。
- **口径一致**：保留 click / hold / flick / drag 全部真实音符（与 `charts.note_count` 对齐），
  **剔除 fake**（假音符不产生击打）；按 `(t, line, ax)` 排序。
- **指纹**：`streamSha = sha256(kind|t|end|ax …)`，用来判断谱面是否真的变过，避免无谓重算。
- **产出**：`notes[]`、`duration`、`lastNoteTime`、`lineCount`、`movingLines`、`counts`。
- **失败情形**：`nofile`（文件缺失）/ `unsupported`（包内不是 RPE 谱面）/ `parse`。
  失败谱面**不写自动值**，pp 自动退回参考定数（当前实例：`42058 Parallel Universe Shifter`）。

## 3. 特征工程（流程②）— `services/chartFeatures.js`（960 行，`FEATURE_VERSION = 2`）

### 3.1 与游戏引擎共享的常量

| 常量 | 值 | 来源/含义 |
|---|---|---|
| `WINDOW_PERFECT` / `GOOD` / `BAD` | 0.08 / 0.16 / 0.22 s | `public/rulaios/js/judge.js` 的 `WINDOWS.standard`（standard 判定窗） |
| `X_DIFF_MAX` | 0.23625 | `judge.js` 的横向容差（世界 x） |
| `NOTE_WIDTH_RATIO_BASE` | 0.13175016 | `judge.js` 的 note 基准宽度 |
| `STREAM_DT` | 0.15 s | 连打（stream）相邻间隔阈值 |
| `JACK_DT` / `JACK_DX` | 0.2 s / 0.06 | jack（同点连打）的间隔上限与落点重合容差 |
| `TRILL_DX` | 0.12 | 交互（trill）两侧最小间距 |
| `CHORD_DT` | 0.025 s | 同刻多押归并（跨线；引擎的 `multipleHint` 只覆盖同线 ±2ms） |
| `CROSS_SCREEN` | 1.0 | 跨屏跳跃位移阈值（世界宽度 2.0 的一半） |
| `FINGER_REST` | `[-0.75,-0.25,0.25,0.75]` | 四指静止位（世界 x） |
| `FINGER_MAX_SPEED` | 13.05 世界 x/s | 单指手速参照上限，见下 |
| `IMPOSSIBLE_EXCESS` | 1.5 | 超过参照上限 1.5 倍记为「物理上做不到」 |
| `HAND_SPLIT` / `HAND_WINDOW` | 0 / 2.0 s | 左右手分界（世界 x=0）与单手段滑动窗口 |
| `DT_BUCKET`/`DX_BUCKET`/`SAME_DT_TOL`/`SAME_DX_TOL` | 0.05/0.1/0.01/0.02 | 重复度记号量化粒度与「两步相同」容差 |
| `SEG_SIZE` / `SEG_STEP` | 10 s / 5 s | 分段窗口与步进 |

`FINGER_MAX_SPEED` 的标定方式（`--finger-speed`）：取标注池里「最简单一档」（定数 < 17.4，
74 张，**全部有成绩 ⇒ 确定被人打通过**）的**全谱最大手速** p95 = 13.047 → 取 13.05。
它是**相对参照值**不是物理上限：四指最近邻贪心会高估真实单指手速，所以只用来给
「超标比例 / 不可达比例」这类计数量定刻度。

### 3.2 G1–G10 指标组

所有特征名带前缀，`groupFeatures()` 就是按 `前缀_` 分组的。

| 组 | 主题 | 代表特征（部分） |
|---|---|---|
| **G1** | 密度 | `g1_npsAvg`、`g1_npsMechAvg`、`g1_nps1sMax`、`g1_maxNotes2s/4s`、`g1_activeRatio`、`g1_gapRatio`、`g1_highDensityRatio` |
| **G2** | 连打（stream） | `g2_dtMin/P10/P50`、`g2_streakMax`、`g2_streakNoteRatio`（最大连打链条与覆盖率） |
| **G3** | jack / 交互 | `g3_jackRunMax`、`g3_jackNoteRatio`、`g3_trillRunMax` |
| **G4** | 多押 | `g4_chordMax`、`g4_chordNoteRatio`、`g4_chord3NoteRatio`、`g4_chordPerSecMax` |
| **G5** | 位移与手型跳跃 | `g5_distP50/P90`、`g5_speedP95/Max`、`g5_crossScreenRatio`、`g5_beyondToleranceRatio`、`g5_handTravelP95/Max`、`g5_handSpeedP95`、`g5_handOverreachRatio`、`g5_sameFingerRepeatMax` |
| **G6** | hold | `g6_holdNoteRatio`、`g6_holdTimeRatio`、`g6_holdLenMean/Max`、`g6_holdOverlapMax/DensityMax/Avg`、`g6_holdMovingRatio`（判定线在 hold 期间移动的比例） |
| **G7** | 读谱/音符类型 | `g7_flickRatio`、`g7_dragRatio`、`g7_fakeRatio`、`g7_lineCount`、`g7_movingLineRatio`、`g7_lineTravelXAvg/Max`、`g7_lineRotAmpAvg/Max`（判定线位移/旋转幅度，每线最多 200 采样） |
| **G8** | 判定紧迫度 | `g8_perfectRatio`、`g8_goodRatio`、`g8_badRatio`、`g8_dtWindowP10`、`g8_tightJackRatio`、`g8_burstMax`、`g8_burstP95` |
| **G9** | 手型可达性 | `g9_handSpeedP99/Max`、`g9_handExcessMean/P90`、`g9_handImpossibleRatio`、`g9_handStepP95/Max`、`g9_handTravel2sMax`、`g9_handJump2sMax`、`g9_crossSideRatio`、`g9_sameSideFastRatio`、`g9_dirChangeRatio`、`g9_sideChordMax`、`g9_sideChord3Ratio` |
| **G10** | 重复度（背板收益） | `g10_bigramRepeatRatio`、`g10_trigramRepeatRatio`、`g10_distinctShapeRatio`、`g10_sameIntervalRatio`、`g10_sameShapeRatio`、`g10_period2RunMax` |

手型模型（G5/G9）：把 4 个指头按 `FINGER_REST` 摆好，对每个音符做**最近邻贪心**分配，
于是能算出「这一下要哪个指头跑多远 / 多快」，再由 `FINGER_MAX_SPEED` 折算成
`overreachRatio`（>1×）与 `impossibleRatio`（>1.5×）。

### 3.3 分段聚合（本文里最重要的特征来源）

- 按 10 s 窗口 / 5 s 步进切段；末尾不足 10 s 未被覆盖时**再补一个以谱面结尾对齐的窗**，
  避免末尾空白把峰值密度稀释。
- 每段算：`nps`、`mechNps`、`dtP10`、`speedP95`、`jackRatio`、`chordRatio`、`chordMax`、
  `handSpeedP95`、`handOverreach`、`handTravel`、`handJump`、`patternRepeat`、`burstMax`。
- 段级 → 谱面级：对其中 10 个度量取 **mean / p90 / max**（`seg_*Mean|P90|Max`），再加
  `seg_peakNps`、`seg_peakPosition`（最难段在谱面的相对位置）、`seg_activeRatio`、
  `seg_headNps` / `seg_tailNps` / `seg_tailHeadRatio`（难度是否堆在开头或结尾）。
- 实测这些 `seg_*` 特征占了模型分裂次数的 **34.6%**——最难段的强度比全谱平均值更能说明定数。

### 3.4 收尾

`meta_duration/noteTotal/mechTotal/fakeRatio` 只进报表、不进模型；
`seg_peakTime/seg_peakEnd`（绝对时间点）同理排除；**全部特征四舍五入到 4 位小数**后入模，
最终模型用 **114 个特征**（原始 120 个）。

## 4. 特征 → 定数（流程③④）— `services/gbdt.js` + `services/difficultyModel.js`

### 4.1 学习器

零依赖的平方损失提升树（`fitGbt`）：预测值 `base = mean(y)`，每轮对残差拟合一棵回归树，
**增益 = 平方和**（`sumL²/nL + sumR²/nR − total²/n`），按 `lr` 累加；每个特征预先排序下标，
节点成员用 mask/stamp 标记，`minLeaf` 被夹到 `样本数/2`。每棵树随机抽 `featureSubset` 个特征
（colsample_bytree，降方差并保证所有特征都有机会被用到）。

当前落库模型标记：**`gbt-2-200x4-s7`**（= 特征版本 2 + 200 轮 × 深度 4 + seed 7）

| 超参 | 值 | 说明 |
|---|---|---|
| `rounds` | 200 | 树的数量（`lr`0.06 × 200 ≈ 有效学习量） |
| `maxDepth` | 4 | 单棵树深度 |
| `minLeaf` | 8 | 叶最少样本 |
| `lr` | 0.06 | 学习率 |
| `featureSubset` | 30 | 每棵树抽的特征数（共 114 个） |
| `seed` | 7 | 同时决定抽特征与 K 折切分，**保证可复现** |

超参是**网格搜索**选出来的（36 组，只看训练集折外 MAE，**绝不拿锚点选超参**）。
同口径对比：岭回归 OOF MAE 0.307 / ρ 0.781，GBDT 0.276 / ρ 0.808。

### 4.2 去收缩（deshrink）

GBDT 的折外预测会被压向均值（收缩），所以用 `5` 折 OOF 预测（`OOF_FOLDS = 5`）
拟合一次单变量最小二乘 `y ≈ slope·p + intercept` 把它顶回来：

- 当前代码复现：`y = 1.0485·p − 0.8651`
- 落库那次（2026-09-24 10:06，训练 361 张）：`y = 1.0232·p − 0.4154`
  （见 `data/difficulty_calibration.json` 的 `model.deshrink`）

`predictOne(fitted, x) = deshrink.slope · GBDT(x) + deshrink.intercept`，**这就是落库值**。

### 4.3 训练标签与样本量

标签 = `charts.difficulty`（参考定数）。训练集 = 「`file_path` 非空 且 `difficulty > 0`」
的谱面，**减掉校准集那 20 张锚点**（锚点只用于第 5 节的验收，绝不进训练）：

| 量 | 当前实测 | 落库那次 |
|---|---|---|
| `file_path` 非空 | 381 | 381 |
| 抽取成功 | 380（1 张 `42058` 包内不是 RPE 谱面） | 380 |
| 其中有参考定数 | 378（另 2 张是段位谱，定数已归零） | 379 |
| 训练样本（去锚点） | **359** | **361** |

### 4.4 训练得到的精度（在标签自身刻度上）

| 指标 | 当前复现 | 落库记录 |
|---|---|---|
| 常量基线 MAE | 0.497 | 0.503 |
| OOF MAE | **0.276** | 0.281 |
| \|误差\| ≤ 0.3 命中率 | 61.3% | 61.2% |
| ρ（Spearman） | 0.808 | 0.803 |

### 4.5 模型实际在用什么（特征重要性 = 被选为切分点的比例）

| 组 | 占比 | | 单个特征 top 10 | 占比 |
|---|---|---|---|---|
| `seg_*`（分段） | 34.63% | | `seg_mechNpsP90` | 2.72% |
| `g9_*`（可达性） | 12.22% | | `seg_mechNpsMax` | 2.67% |
| `g5_*`（位移手型） | 11.35% | | `g6_holdOverlapDensityMax` | 2.09% |
| `g7_*`（读谱） | 10.48% | | `seg_handSpeedP95Mean` | 2.04% |
| `g6_*`（hold） | 8.05% | | `seg_patternRepeatMean` | 2.04% |
| `g1_*`（密度） | 6.06% | | `g7_flickRatio` | 1.99% |
| `g8_*`（判定紧迫） | 4.36% | | `g5_distP90` | 1.84% |
| `g10_*`（重复度） | 4.32% | | `g7_lineRotAmpAvg` | 1.79% |
| `g2_*`（连打） | 3.10% | | `g3_jackNoteRatio` | 1.70% |
| `g4_*`（多押） | 3.01% | | `g5_crossScreenRatio` | 1.65% |
| `g3_*`（jack） | 2.42% | | | |

> 「最难段的机械连打密度 + 手速 + 背板重复」是模型的主轴；纯密度（G1）只排第 6。

## 5. 口径标定与验收（旁路，**不参与落库**）— `--score`

体感分比旧定数表系统性低约 0.25，这个差异用一个仿射表达：

```
体感分 ≈ 0.8346 · d + 2.6891      （d = 旧定数表定数；用 20 张锚点拟合，逐点改用留一系数）
```

- **锚点**：分层抽样 20 张（6 档，每档保底 2 张，`seed 20260301`），池子限定
  `source='official'` + 有谱面文件 + 定数 > 0 + 时长 60–180 s + 排除 charter 含 `rulai`；
  体感分由人填写在 `data/difficulty_ratings.csv`（`--score --ratings`）。
- **必须留一**：`looOffsetApply()` 对每个锚点用「其余 19 张」拟合的口径，避免自我泄漏。
- **验收线**（2026-09-24 定）：不是硬性 70%，而是 **标签天花板 − 1 张**。
  理由：训练标签就是旧定数表，任何以它为标签的模型都不可能超过天花板。
  `passLine = max(1, ceiling.count − PASS_SLACK)`，`PASS_SLACK = 1`，容差 `HIT_TOLERANCE = 0.3`。

当前结论（`data/difficulty_calibration.json` 的 `calibration`）：

| 对象 | 命中 /20 | MAE | ρ |
|---|---|---|---|
| 模型原始预测（定数刻度） | 50% | 0.456 | — |
| 旧定数表（参照，非真值） | — | — | — |
| 模型 + 口径（留一） | **60%（12）** | 0.406 | 0.675 |
| 旧定数表 + 口径（留一）= **天花板** | **70%（14）** | 0.288 | 0.866 |

`passLine = 13` → **`passed: false`（差 1 张）**。

⚠️ **两点容易误读**：
1. `passed` 只写在报告里，`--apply` **没有门槛**，不会因为未达标就拒绝落库。
2. **口径仿射不参与 PPSR**。落库值 = `去收缩(GBDT(x))`，与旧定数表**同刻度**，
   这样才能和参考定数直接比较、也才符合 pp 公式原本的定数标定。
   口径只在「与体感分比对」这一步用（`--predict` 输出时明确打印「predicted 与旧定数表同刻度，
   口径换算在 --score 里做」）。若把口径并进 PPSR，等于额外给所有定数做一次整体缩放。

## 6. 落库（写入 `chart_auto_difficulty`）— `scripts/difficulty_calibration.js --apply`

```sql
CREATE TABLE IF NOT EXISTS chart_auto_difficulty (
  chart_id    TEXT    NOT NULL PRIMARY KEY,
  value       REAL    NOT NULL,
  model       TEXT    NOT NULL,          -- 如 gbt-2-200x4-s7
  computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

- 全池（`file_path IS NOT NULL`，含**没有参考定数**的谱面）逐个预测后 upsert，**幂等**；
  没有定数的谱面只落库、不参与训练 —— 它们从这天起可以参与 pp（段位谱除外）。
- 落库同时打印：与人工定数的 MAE/命中/平均偏差/ρ、偏差最大的 10 张、
  相对上一次落库值有变化的张数、分档直方图与值域。
- **回滚**：`DELETE FROM chart_auto_difficulty` → `resolveDifficulty()` 第①步失效，
  pp 立刻回到参考定数，代码不用改。

**当前库里状态**：383 行，`model = 'gbt-2-200x4-s7'`，`computed_at = 2026-09-24T10:06`，
值域 16.14 ~ 19.995。其中 380 行对得上当前可抽取的谱面，另 **3 行是历史遗留**
（`8742`、`14863`、`39209`：谱面被删除或 `file_path` 被置空）——不参与 pp（pp 按 chart 关联取），
可随时用 `DELETE` 清掉。

## 7. 运行时取值与消费（流程⑤）— `services/difficulty.js`

优先级（`resolveDifficulty(chart, constants, auto)`，返回 `{difficulty, source}`）：

```
① chart_auto_difficulty_override.value   人工修正（超管，routes/autoDifficulty.js）  source='auto'
①' chart_auto_difficulty.value           算法输出（loadAutoDifficulties 已叠加①）    source='auto'
② charts.difficulty                      参考定数兜底（算法没算出来的谱面）         source='charts'
③ chart_constants                        社区定数表兜底                             source='chart_constants'
④ 都没有 → {null, null}                  不参与 pp
```

`> 0` 才算有效值（0 / 负数 / NaN 一律当作「没有」）。表缺失时 `loadAutoDifficulties()`
返回空表而不抛错（老库可用）。

消费点：

| 位置 | 用法 |
|---|---|
| `routes/scores.js` `computeAndSnapshot()` | 定数解析 → `matched[].sr`，段位谱直接跳过 → `services/pp.js` `calcTotalPP()` |
| `services/phiraSync.js` | 同步 phira 成绩时同一条链 |
| `scripts/refetch.js` | 手动重算某玩家 BP（`node scripts/refetch.js <用户名\|id>`，用户名要完全一致） |
| `routes/charts.js` | 谱面池/谱面详情：`display_difficulty = 解析值`、`ppsr = 段位谱 ? null : 解析值`、`ppsr_source` |
| `routes/users.js` | BP 明细：`sr`(=PPSR) + `ref_sr`（`attachReferenceDifficulties()` 现算，历史快照也能显示参考定数） |
| `routes/ranked.js` / 段位页 | `resolveDisplayDifficulty()`：人工定数优先，缺失（段位谱恒为 0）用自动值兜底 |

pp 怎么用这个数（`services/pp.js`，与 `phira_pp/pp.py` 默认参数一致）：

```
单曲 pp = BASE × sr^6 × accFactor × precisionFactor × errorFactor
  BASE = 1000 / 18^6 ≈ 2.9401194e-5；sr = PPSR
  accFactor       = acc < 0.70 ? 0 : ((acc − 0.70)/0.30)^4
  precisionFactor = 由 std 决定，0.01538s→1.04、0.02707s→0.96；std ≤ 0 或 > 0.2s 取 1.0
  errorFactor     = (1 − (bad+miss)/总键数)^3；缺 P/G/B 计数时取 1.0
总 pp = Σ(i=0..99) pp_i × 0.95^i     （按单曲 pp 降序取前 100 条）
```

注意 **sr 的 6 次方**：定数差 0.6 就能让单曲 pp 变化约 20%，所以 PPSR 的小数点后两位是有意义的，
历史快照的 pp 会随「落库时用的哪一套定数」而不同（快照不会自动重算）。

## 8. 人工修正层（只有一个人能动）

```sql
CREATE TABLE chart_auto_difficulty_override (
  chart_id TEXT PRIMARY KEY, value REAL NOT NULL, note TEXT, updated_by INTEGER, updated_at DATETIME
)
```

- 由 `routes/autoDifficulty.js` 写入（超管），`services/difficulty.js`
  的 `setAutoDifficultyOverride()` / `clearAutoDifficultyOverride()` 校验
  `0 < value ≤ 30`、四舍五入到 3 位。
- `loadAutoDifficulties()` 里修正值**整体覆盖**算法值（`Map.set`，所以也能给算法算不出的谱面补值）。
- **改的是「实际计算时用多少」，不动算法**：`--apply` 重算全池不会覆盖这张表；
  撤销 = 删行，界面立刻回到算法值。
- 当前唯一一条：`chart_id 39209 (Fallen Symphony) = 19.395`（用户 1，2026-09-24 10:38 UTC）。

## 9. 复现 / 运维命令

```powershell
# 全池重算并落库（约 1 分钟：抽取 380 张谱面 ≈ 40 s + 训练）
node scripts/difficulty_calibration.js --apply

# 只跑锚点预测（不写库），结果落到 data/difficulty_calibration.json
node scripts/difficulty_calibration.js --predict

# 锚点验收（需要人工体感分 data/difficulty_ratings.csv）
node scripts/difficulty_calibration.js --score --ratings data/difficulty_ratings.csv

# 重新抽样锚点（会覆盖 json；ratings 模板已存在则不覆盖）
node scripts/difficulty_calibration.js --sample --n 20

# 重新标定 FINGER_MAX_SPEED（输出建议值，需手写回 services/chartFeatures.js）
node scripts/difficulty_calibration.js --finger-speed

# 单张谱面看音符流/特征/分段（调试用）
node scripts/auto_difficulty.js --chart <本地 id 或 chart_id> [--features]

# 重新计算某玩家的 BP（自动定数改了之后必须做，否则快照还是旧值）
node scripts/refetch.js <用户名>
```

常量与参数**只写在一处**（`services/chartFeatures.js` 顶部与
`services/difficultyModel.js` 的 `MODEL_CONFIG`），本文的数字与代码同步于
`data/difficulty_calibration.json` 的 `featureVersion 2 / hitTolerance 0.3`。

## 10. 已知偏差与维护注意

1. **训练标签的滞后**：`charts.difficulty` 不变时重新 `--apply` 结果基本一致；但**标签一变**
   （例如段位谱定数归零、导入新定数表），模型就会小幅漂移。当前库里那 383 行是 361 张标签
   训练出来的，而今天重训是 359 张（两张段位谱归零）→ 去收缩系数从 `1.0232/−0.4154`
   变为 `1.0485/−0.8651`，个别谱面会有 ~0.1 的差别（例如 `42058` 之外的同档谱面）。
2. **1 张谱面永远算不出**：`42058 Parallel Universe Shifter` 的 `.pez` 里没有
   `judgeLineList`，抽取器判定 `unsupported`；它的 pp 走参考定数 18.8。
3. **孤儿行**：`chart_auto_difficulty` 里可能有谱面已删除的行（如 `8742`），无害但会污染统计口径。
4. **未达验收线**：锚点 12/20 vs 天花板 14/20（`passed: false`）。当前**没有**为达标而调参；
   如果要把差距补上，改动方向应是特征（尤其 `seg_*` 与 G9 手型模型）而不是超参——
   超参一旦按锚点选，锚点就不再是独立验证集。
5. **段位谱**：定数归零、不进 pp、不参与训练；界面显示与 pp 口径由
   `resolveDisplayDifficulty()` / `display_difficulty` 两处分别负责，改动时注意不要互相污染。
