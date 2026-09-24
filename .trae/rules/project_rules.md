# 项目规则

## 最高原则：禁止想当然，一切以真实数据为准

1. **禁止任何基于猜测、臆断或经验预期的实现与修改。**
   - 字段含义、单位、坐标系、公式、常数的取值，在动手写代码前必须先核实来源：官方文档 / 参考实现 / 真实样本数据三者之一。
   - 不允许“先按猜的写，跑出来再看效果”。

2. **所有设计方案必须由明确且真实的数据支撑。**
   - 每新增一个特征、公式项、常数或权重，都必须能同时给出：
     - **数据来源**：具体是哪张谱面、哪条成绩记录、或哪份官方文档；
     - **验证方式**：可复现的检查或对照（脚本 + 指标）。
   - 无法给出上述两者的改动不得合入。

3. **验证口径必须落在真实数据上。**
   - 解析类改动：解析结果必须与真实成绩对照。例：解析出的有效键数应与排行榜 AP 记录的 `Perfect + Good + Bad + Miss` 完全吻合。
   - 统计/拟合类改动：必须报告样本量、数据筛选口径与指标（R²、RMSE 等）。
   - “看起来合理/符合直觉”不构成证据；必须给出可复现的数值或对照。

4. **失败必须显式暴露。**
   - 解析失败、数据缺失、格式不支持等情况要明确记录并计入统计，禁止静默兜底掩盖问题。

5. **不确定就停下来查，而不是猜。**
   - 遇到不确定的语义（如事件层级叠加规则、坐标单位），先查文档/参考实现，或用真实样本统计其使用情况，再决定实现方式。

## 技术约定

- **解释器**：使用项目内虚拟环境 `.venv`。
  系统 PATH 上的 `python` 是损坏的 Microsoft Store stub，用户级 numpy 也损坏，**不要使用**。
- **运行脚本**：在项目根目录执行
  `$env:PYTHONPATH="."; .\.venv\Scripts\python.exe <script>`
- **启动方式（固定）**：
  - 网页界面：运行 `start.bat`（会自动打开浏览器；可加 `--port`；端口被占用会明确报错而非静默双开），
    地址 `http://127.0.0.1:8000/`；**必须经该 http 地址访问，不要直接双击 `web/index.html`**
    （`file://` 下所有 `/api/*` 请求都会失败）。关闭服务：在该窗口输入 `off` 并回车（无需 y/n 确认）。
  - 命令行：`$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\pp.py <chart|record|user|play|best> ...`
  - 登录拿 token：`$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\login.py`
    （凭据本地输入、不回显、不落盘；token 存入 `data/.token`，已被 .gitignore 忽略）
- **依赖**：见 `requirements.txt`（requests、numpy、scipy）。
- **数据缓存**：抓取到的谱面包与特征存于 `data/`（`packages/`、`features/`、`difficulty_model.json`）。
  每个 `features/<id>.json` 还携带 `_difficulty`/`_ranked`/`_rating_count` 三个**标签/来源**字段，
  它们是 D\* **训练集**的唯一来源（`fit_difficulty2.py` 按 `_difficulty` 组装标签）；
  **查分/PP 完全不需要它们**（D\* 预测只吃特征）——所以缺标签只影响训练，不影响任何分数。
  ⚠️ 踩过坑：`Dataset.get_features` 命中缓存时曾直接 `return`、从不回写标签，导致缺失的标签**永远补不回来**，
  而 `build_train_set.py` 的"回填"正是调用它 → **静默空转**（实测 225 个文件长期无标签、无人知晓）。
  已修：命中缓存但缺 `_difficulty` 时，用传入的 meta 补写并落盘。
  修复工具：`scripts/backfill_feature_labels.py`（默认 dry-run，`--apply` 才写；
  实测 225/225 全部补回，Phira 端 0 缺失）。修复后可用标签 **828 → 1022**（D\* 训练集）。
- **纯网页单文件版**：根目录 `PhiraPP.html` 由
  `$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\build_standalone.py` 生成
  （= `web/standalone.template.html` 注入社区定数表 `id→定数`：`data/kv_diff.json`，
  再用 `data/subjective_diff.json` 补 Suonasi 未覆盖的 id（Suonasi 优先）；约 26 KB）。
  浏览器**直连** Phira API（实测 CORS `Access-Control-Allow-Origin: *`，含 `file://` 的 `Origin: null`），
  无需 Python/服务端，双击即可用；两个主机 `phira.5wyxi.com` / `api.phira.cn` 轮询以突破浏览器单源连接数上限。
  - **硬限制**：浏览器算不了自研 `D*`（需 Python 解析谱面包 + 模型），故单文件只支持
    ranked 谱与社区定数谱（442 张）；其它谱在单查询里**明确提示**而非猜测。
  - 验证口径：`node scripts/verify_standalone.mjs <id>` 复用单文件自身的 JS 跑一遍，
    与 `scripts/pp.py best <id> -n 100` 的「总 PP」对拍（实测 459003：**20463.2 = 20463.2**；
    构建时会把「主观表当下限」的 D\* 一并烘进表里，故两边口径一致）。

## 设计约定

- **PP 的难度取值**（按优先级）：
  0. **专家覆盖层** `data/difficulty_override.json`（优先级最高；`ranked` 谱师定数仍压过它）——
     D\* 是对定数标签的**最小二乘拟合**，**对标签只有 18.4/18.56 的谱不可能输出 19.4**，
     所以「故意偏离」必须做成**显式策略项**，不得伪装成拟合结果
     （参考实现 PPSR 同样用它给 `#39209` 挂 19.395，且那是它全库唯一一条人工 override）。
     当前五条（项目主给定，2026-09）：`#22206 = 19.40`、`#39209 = 19.60`、`#14863 = 19.50`
     （体感 19.5+，谱师定数 19.00 / D\* 19.18 都偏低）、`#54540 = 18.50`（D\* 19.19，
     51 秒 10000 键 / 92% drag 堆叠墙，虚高来自「短而密」约 +3.7）、`#50333 = 18.00`（D\* 18.81，
     谱师写的 20.00 已当离群剔除）。单文件构建时一并烘进表里。
     校验：`scripts/verify_subjective.py` 的 override 断言。
  1. `ranked` 谱 → 谱师定数；
  2. 否则若在 `data/kv_diff.json`（SuonasiOS App 的 KV 服务
     `https://suonasi.07210700.xyz/kv/diff`，来源：反编译其 `libapp.so` 得到；
     机读 TSV `id/name/diff/badge/cover`，**自动跳过 `-1` 开头的本地谱**）中 → 定数表值（Suonasi）；
  3. 否则若在 `data/subjective_diff.json`（主观定数表，来源：用户提供的
     `data/subjective_diff.xlsx`「phira 高难自制谱面参考性主观定数表」，
     由 `scripts/build_subjective_diff.py` 解析）中 → 定数表值（主观）；
     **与 Suonasi 重复的 id 一律取 Suonasi 值**（表主明确要求）；
     **且主观表值只作「下限」**：该表自述「不会对 18.60 及以上进行定数」，无法表达顶部，
     故当 D\* 合法（见下条容差）且高于表值时取 D\*（`_table_with_floor`，来源标记 `D* (高于主观表)`）。
     实测只升 7 张、不降任何谱：#22206 18.56→20.00、#39209 18.59→19.84、#30942 18.56→19.34、
     #14480/#36301/#25523/#26017 小幅上调。Suonasi 值**不**当下限（保持原样）。
  4. 否则 → 自研客观难度 `D*`。
     合并逻辑见 `phira_pp.pipeline.load_tables`；两表都不存在时才回退旧 OCR 集 `data/anchors.json`。
  依据（已实测）：KV 表 405 条有效 id（17.0–19.3）；主观表 172 条记录中 148 条有上架谱编号
  （24 条为 `/` 本地谱，丢弃），定数 17.55–18.59；两表重叠 111 个 id，主观表净补 37 个 id，
  合并后共 **442** 张。11 个上架 id 在 Phira 端 404（谱面已不存在），保留在表中但天然失效。
  校验：`scripts/verify_subjective.py`（逐条断言 + 打印主观 vs D\* 对照 + 下限规则 3 例）。
  ⚠️ 主观表自述「不会对 18.60 及以上进行定数」，其高难端被压缩在 18.59 以下 —— 这正是「只作下限」的原因；
  因此**不要**把它当 D\* 的上界。
- **Phira 查分接口（逆向 + 真实数据实测所得）**：
  - API 主机 `https://phira.5wyxi.com`（与 `api.phira.cn` 同源）；`services/phira_api.dart`。
  - **玩家×谱面（关键直通接口，已实测）**：`GET /record?player={uid}&chart={cid}`
    - **无需 token，任意玩家可用**；返回该玩家在此谱上的成绩数组（≤20 条），
      **必定包含其最好成绩**（`best: true`），并带 `std`（无暇度）、`score`、`accuracy`、
      `perfect/good/bad/miss`、`max_combo`、`speed`、`mods`、`time` 等完整字段；未游玩 → `[]`。
    - 验证：随机 18 张谱，`max(score)` 与权威 `/record/best/{chart}` **全部一致（0 处不符）**，
      且每张返回行都含 `std`。故这是完整、无排名深度盲区的查询方式。
    - `best` / `play` 都改走它（每谱一次请求，`ThreadPoolExecutor` 并发）。
    - **取哪一条？取 PP 最高的那条，不是分数最高的**（见下条「成绩选择口径」）。
    - 注意：重复 `chart=` 参数是「后者覆盖」而非并集，**无法一次请求查多张谱**。
  - `GET /record?player={uid}`（对应 `fetchRecentRecords`）：最近 20 条（含 `std`）。
    `order=<字段>` 仅接受 `score`/`time`（`-score` 为降序）；**page/pageNum/offset/cursor 等分页参数全部被忽略**，
    恒返回 20 条，故**不能**用来拉取全部成绩。
  - `GET /record/best/{chart}`：路径段是**谱面 id，不是用户 id**；需 `Authorization: Bearer <token>`，
    返回 token 本人在该谱的 `{score,accuracy,fullCombo}`（55 字节；未游玩为 `score:0`），**不含 `std`**；
    传用户 id 会 404（不存在该谱）。仅用于「是否玩过」的快速探测。
  - `GET /record/query/{chart}?page=&pageNum=`：谱面排行榜，按分数降序，`pageNum` 上限 30；
    `player=` / `includePlayer=true` / `charts=` 等筛选**均被忽略**（实测），无法定位某人成绩。
  - 无效路径：`/record?user=`、`/record?userId=` 被忽略；`/record/{uid}/...`、`/user/{uid}/records` 等 404。
  - **登录载荷**：`POST /login` + JSON `{"email","password"}`；已实现 `scripts/login.py`
    （凭据仅本地输入，token 落 `data/.token`）。**现直通接口不需要 token，登录已非必需**。
- **不要依赖抓包**：SuonasiOS 是 Flutter 应用，走 Dart `dart:io` 自带的 TLS 栈
  （libapp.so 内含 `dart:_http`/`_HttpIncoming`/`RawSocketEvent`/`SocketOption`），
  用户级安装的代理 CA 不被其信任，故 Charles / Stream / Proxyman 之类抓不到明文；
  如需抓包必须做 TLS trust/pinning 绕过（Frida：hook `SecTrustEvaluateWithError`，或 objection
  `ios sslpinning disable`）。拿到 token 的正路是本地登录，不是抓包。
- **已知硬限制（高难端已部分修复）**：全目录 `ranked+reviewed` 中定数 17+ 的谱仅约 10 张，故高难端（18+）的系统性低估（基线实测偏差 **−0.55**）**无法靠谱师定数修复**；放宽到未审核谱会引入垃圾标签（实测 CV 反而下降）。**已用主观定数表的 135 张谱当训练标签修复**（见 D\* 修正 ③：偏差 −0.55→−0.39、RMSE(≥18) 0.786→0.700）。
- **D\* 的四处修正（真实数据实测）**：
  1. **标签清洗（robust trim）**：训练标签里存在**占位/虚标**——27 张 ranked 谱的定数写作 `0.0`
     （那是 Phira 的「未设定定数」占位符，不是 0 级），以及 `#39209 Fallen Symphony`（nps=121、10000 键）
     被填成 `1.9`、`#71519 Acht Streiks`（nps=42）被填成 `3.5` 等。
     按残差（>2.5×稳健 σ=0.76）剔除 59/722 张不一致标签后：**CV R² 0.357 → 0.836**，
     嵌套 CV（裁剪在每折内重做，无信息泄漏）**0.817**，RMSE 0.84 → **0.686**。
  2. **新增「排列整齐度」特征**（`dt_cv` onset 间距离散度 / `dir_change_p80` 走位转向 / `aim_p99`）：
     在清洗后的样本上逐个通过前向选择（CV 0.696→0.719→0.744→0.756），已并入 `FEATURE_NAMES`（共 16 个）。
     效果：**`nps_peak` 权重从 +0.121 降到 −0.024**（峰值密度不再驱动难度），
     `dir_change_p80 +0.294`、`dt_cv +0.238` 进入前六 —— 「密度大但排列整齐」不再被高估。
  3. **主观定数表当训练标签 + 剔除退化谱**（`scripts/fit_difficulty2.py`；受控对照 `scripts/exp_subjective_labels.py`）：
     把 `data/subjective_diff.json` 的谱**按其表内定数**加入训练（**不是**谱师定数——同一批谱改用谱师定数反而更差）。
     受控实验（固定谱师标签测试集，5 折 × 5 种子，α=30 固定，两臂都剔除退化谱，标签补齐后 n=815）：
     `只用谱师标签` R² 0.835 / RMSE 0.692 / RMSE(≥18) 0.786 / 偏差(≥18) −0.55；
     `+ 表内定数` **0.835 / 0.692 / 0.700 / −0.39**（高难端 RMSE −11%、低估偏差收窄 29%）；
     `+ 谱师定数` 0.800 / 0.762 / 1.034 / −0.87（更差）。
     生产重训（同一训练集内 CV）：0.839 → **0.849**，nested **0.841**，in-sample R² 0.868 / RMSE 0.637，
     共 **949** 张（814 谱师 + 135 主观）。
     **附带重大修复**：剔除 `#54540`（实测是 4346+3000 个同时 drag 的"墙"，`nps_peak`=7376、`chord_max`=7346）
     后，`nps_peak` 的 σ 从 286.6 → **30.0**、`chord_max` 从 285.0 → **9.97**、`chord_mean` 从 0.683 → 0.282
     —— 此前这三个特征的标准化被单张谱主导，等于被废掉（`chord_max` 权重也因此从 −0.021 翻到 +0.039）。
     **代价（实测全 1082 张缓存谱，对比上一版模型）**：|ΔD\*| 中位 **0.039** / p95 0.141 / max 0.848；
     **0 张**新越界。`pipeline.chart` 现已**对单谱查询同样执行 [0,20] 越界排除**
     （此前只有 `best_plays_full` 有该保护，单谱查询会直接吐出 41.31 → 15 万 pp 的假分）。
  4. **两道输入护栏：clip（含密度上限）+ 物量饱和 hinge**（`phira_pp.difficulty.prepare_features`；实测 `scripts/exp_saturation.py`）：
     - **clip**：每个特征先裁剪到**训练集观测区间**（存于模型 JSON 的 `clip`）。否则单张谱无界外推——
       `#54540` 的 `chord_max`=7346 而全库上限 170（z=+736），光这一项就 +28.4、D\*=40.5。
       clip 对区间内的谱是**恒等变换**，不改变拟合。
     - **密度上限**（`DENSITY_CAP`，同一 clip 机制）：`nps_peak ≤ 50`、`chord_max ≤ 12`。依据是**标签本身**：
       `nps_peak` 30-40 档 16.63 → ≥50 档 17.10 → ≥100 档反而 16.71；`chord_max` 10-20 档 17.10 → ≥15 档 16.36
       —— 超出后不再上升，属堆叠/瞬移产物（`#54540` 是 4346+3000 个同时 drag 的墙）。
     - **hinge**：`le_hinge = max(0, log_eff − 3.4)`（第 17 个特征）。依据：定数随 `log_eff` 上升到 **3.4 后不再上升**
       （分档均值 17.10 → 17.88 → 17.83 → 18.20 → 17.76），而 `log_eff` 权重最大且 σ 小，会把「键数最多」的谱
       一律顶到 ~20（可它们的标签只有 ~18.6，模型拟合不动）。拟合出的 hinge 权重 **−0.1202**（负 = 饱和，方向与数据一致）。
     - 效果：CV **0.849 → 0.860**、nested **0.841 → 0.854**、in-sample RMSE **0.637 → 0.625**；
       `#54540` 40.47 → **19.66（回到可计分！）**、`#22206` 19.96 → **18.99**（≈表内 18.56）、`#3007` 20.60 → 19.75、
       `#39209` 19.87 → 19.18、`#31028` 20.33 → 19.71、`#71645` 19.89 → 19.26。全库越界谱 **3 → 2 张**（`#10502`、`#26558`）。
       hinge 取 3.8 实测更差（CV 0.858、`#54540` 又越界）故取 3.4。
  复现链：`scripts/collect_subjective_features.py`（拉取主观表谱面特征）→ `scripts/exp_subjective_labels.py`（受控对照）
  → `scripts/exp_saturation.py`（clip/hinge 对照）→ `scripts/fit_difficulty2.py`（重训并落盘 `data/difficulty_model.json`）。
  特征重算链：`scripts/reextract_features.py` → `diag_dstar*.py`。
- **与参考实现（PPSR，用户提供的 `PPSR.md`）的差距审计（1–4 条已做，第 5 条未做）**：
  1. **判定线旋转：已修（2026-09，`FEATURES_VERSION = 8`）**。原始 RPE 的 `rotateEvents` 是**度**
     （实测 #10608 取值 0/3/−3/**270**），此前 `lineevents.rotate()` 原样返回（无 deg→rad），
     且 `features._world_positions` **只加线位移、不做旋转投影**（`wx = px + n.x·half`、`wy = py`），
     缺参考方案的 `ax = worldX + x·cos(rot)` / `ay = −worldY + x·sin(rot)`。
     现已在 `_world_positions` 做 `math.radians()` + 投影，`ROT_Y_SIGN = -1.0`（+1/−1 两符号都做了全量重算 + CV：
     −1 的 CV 0.857 / RMSE 0.622 略优于 +1 的 0.856 / 0.628）。
     `line_rot_p90` 也由「假 rad/s」变为真 rad/s（p50 **17.8 → 0.311**、max 245000 → 4276）。
     ⚠️ **但它不是点名谱面失准的原因**：对 `#22206`/`#39209` 的 D\* 只改变 **−0.01**，CV 在噪声内（0.860→0.857）。
     重算工具新增 `scripts/reextract_features.py --force`（改特征常量但版本号未变时必须用它）。
  2. **分段（最难 10s 窗）聚合：已做（`FEATURES_VERSION = 9`）**。10s 窗 / 5s 步进 + 末尾对齐窗，
     前向选择（`scripts/exp_segment.py`）采纳 `seg_nps_p90`：带上密度上限后 CV **0.859 → 0.861**。
     关键：其拟合权重 **+0.3707**（第 4 大），并把 **`log_eff` 权重从 1.3980 压到 1.1765（−16%）**
     —— 「物量」不再单独承担难度（这正是项目主抱怨的「物量权重过大」）。
     ⚠️ **必须与 `nps_peak` 用同一条密度上限（≤50）**：不加限时它会把 `#54540` 推到 22.30（51 秒纯爆发）。
     其余候选被否：`seg_nps_p50` 0.856 / `seg_nps_max` 0.860 / `seg_speed_p95_mean` 0.860 / `seg_speed_p95_max` 0.861。
     生产重训：CV 0.857、nested 0.850、in-sample R² 0.874 / RMSE 0.619（949 张）。
  3. **手型/可达性：已做（`FEATURES_VERSION = 10`）**。`_hand_stats` 做四指最近邻分配
     （`FINGER_REST=[-0.75,-0.25,0.25,0.75]`、`FINGER_MAX_SPEED=13.05`，单位同为「半屏宽=1」，可直接沿用参考值），
     产出 `hand_step_p95` / `hand_speed_p95` / `hand_overreach_frac`。前向选择（`scripts/exp_hand.py`）
     CV **0.861 → 0.865** 采纳 `hand_step_p95`（另两者 0.863 / 0.860 未采纳）。
     生产重训：CV **0.859**、nested **0.854**、in-sample R² 0.875 / RMSE **0.606**（949 张）。
  4. **时长项：实测证明不能改成正值（保留拟合的负权重）**。同一训练集 / 同折 / α=30：
     保留（**−0.3623**）CV **0.865**；删掉（=参考方案的做法）**0.848**；强加正耐力 λ=0.1/0.2/0.3 → **0.840 / 0.831 / 0.820**。
     ⚠️ **负系数的含义不是「越长越简单」**——它固定的是**总物量**：同样的按键数摊到更长时间 = 更稀疏 = 更简单。
     **同密度下变长，模型是变难的**：时长 ×2 且密度不变 → `log_eff` +0.301（z=+1.14）贡献 **+1.34**、
     `log_duration` +0.301（z=+1.91）贡献 **−0.73**，**净 +0.61**。
     （项目主对「−0.38 越长越简单」的不满源自我的简化表述，已在 `docs/formula.md` 更正并写明推导。）
  5. **学习器**：参考用 GBDT（200×4、114 特征、OOF MAE 0.276 / ρ 0.808）；我们用 17 特征的线性岭回归 + 手加 clip/hinge。
  6. ⚠️ 参考方案里的 **`39209 = 19.395` 是人工 override**（全库唯一一条，因该谱文件缺失算不出），
     不是模型输出 —— 引用它当「模型也这么认为」是错的。用户对 #22206 的期望（≥19.4）与其**自己给的主观表 18.56 冲突**。
     参考方案的 `41913`/`8742`/`14863` 等孤儿行同理，不参与 pp。
- **物量按按键类型加权（专家策略，已验证 CV 无损）**：Phira 的 hold **没有尾判**，所以 hold 只相当于
  「占一根手指的 tap」，短到可点一下就抬起的短长条应**略低于 tap**。权重顺序
  `long_hold > tap > short_hold > flick > drag` 来自项目主的专家判断；
  `TYPE_WEIGHTS = {tap 1.00, long 1.05, short 0.95, flick 0.60, drag 0.50}` 的**量级**来自
  `scripts/fit_type_weights.py` 的 CV 网格搜索；`SHORT_HOLD_SEC = 0.15`（实测 175,394 个 hold 的 p40）。
  受控 A/B（`scripts/ab_logeff.py`，同一裁剪集 / 同折同种子）：`log_eff` 0.837 / nested 0.821
  vs `log_notes` 0.836 / 0.817 —— **统计上无差异**，故采纳（模型 16 特征，`FEATURES_VERSION = 7`）。
  ⚠️ 但它**不改变**此前点名谱面的 D*：因为模型早已用 `drag_frac` 表达了同一信息，重拟合会重新平衡；
  **换任何特征形式都无法在不破坏拟合的前提下改动那些谱**。要动那些谱只有两条路：**换/加训练标签**（见修正 ③）
  或**显式策略覆盖**（λ 可调、界面/规则里标注），不得伪装成拟合结果。
- **D\* 的能力上限与已否决方向（不要再重复尝试）**：D\* 是对谱师定数的拟合，其输出**必然贴近谱师定数**
  （实测对点名的 7 张平均 |差| ≈0.7，与 RMSE 同量级）。以下方向在清洗后的 663 张样本上**全部被 CV 否决**：
  判定线特征（速度/旋转/隐藏，≤+0.007，含仅 RPE 子集）/ 密度饱和（平方崩到 −9.9、换对数 −0.179）/
  按 onset 计数（−0.134）/ 分类型物量分解（−0.034）/ 交互项（≤+0.009）/ 稳健密度（−0.008）。
  另有**「长度/耐力奖励」被数据否决**：`log_duration` 的拟合权重是**负的**（−0.63/σ，同样物量越长越简单），
  且删掉该特征 CV 会从 0.842 掉到 0.777 —— 在线性模型里系数符号**就是**数据给的答案，没有"加长度奖励"这个自由选项。
  实测长谱也**没有系统性低估**：残差 vs `log_duration` 相关 +0.06，最长档（`log_duration` 2.5–2.9）反而平均 +0.79 高估。
  复现：`scripts/diag_length.py`。
  且实测「用户点名高估」的谱**不存在一致特征规则**（高估组里既有 Drag 占 92% 的，也有 100% 纯 tap 的；
  低估组与高估组只在 multi_frac 上有重叠差异），拟合它们等于拟合个人口味。
  要真正偏离谱师定数，必须做成**显式策略覆盖项**（λ 可调、并在界面/规则里标注），不得伪装成拟合结果。
- **训练协议两条铁律**（踩过坑）：① **不得用被评估的模型自身去裁剪训练标签**——会造成
  「plain CV 0.573 / nested CV 0.815」这种自相矛盾；裁剪须用固定的参照特征集（现用原始按键计数）。
  ② ridge 的 `alpha` 取**固定值 30**，不要在近乎平坦的 CV 曲面上 argmax（会选中欠正则的过拟合点）。
- **公式总览文档**：`docs/formula.md` 汇总当前生效的全部变量、参数、难度取值链与 D\* 的 16 个特征权重
  （数值直接取自 `pp.py` / `features.py` / `pipeline.py` / `data/difficulty_model.json`）。
  **改动上述任一来源后必须同步该文档**，校验口径：文档表格里的 57 个特征数值（19 特征 × w/μ/σ）+ 11 项参数
  须与源码逐一吻合（`scripts/verify_formula_doc.py` 自动核对，必须输出 “consistent with the source”）。
- **展示类常数**（`ref_pp`、`ref_diff`、`diff_exp`）无数据真值，属可调策略参数，必须显式标注。
  当前 **`diff_exp = 6.0`**（由 2.0 上调；理由：单曲 PP 拉不开差距、低难度给太多）。
  实测（`scripts/sweep_diff_exp.py`，459003 的 338 条真实成绩）：`exp=2.0` 时 b1–b100 天地差 144、
  最低采用定数 17.00；`exp=6.0` 时差 296、低于 18.0 的谱被挤出 top100；各档位倒挂均为 0。
- **准确率曲线 `acc_pow` 也是策略参数**：当前 **4.0**（由 2.0 上调；理由：97%/98% 惩罚太小、拉不开差距）。
  实测（`scripts/sweep_acc_pow.py`，diff_exp=6，459003 的 338 条成绩）：
  `p=2` 时 acc97%→0.810、天地差 296 / b1b100 1.319；`p=4` 时 97%→0.656、差 308 / 1.370；
  `p=5` 时 97%→0.591、差 337 / 1.422。各档位「1.0 定数步长」倒挂均为 0。
- **无暇度轴幅度 `precision_weight` 也是策略参数且受约束**：须满足 `(1+w/2)/(1-w/2) < (19/18)^diff_exp`，
  即「1.0 定数步长」不得被无暇度摆幅盖过（无暇度与难度正相关，摆幅过大会系统性抵消难度收益）。
  实测（`scripts/sweep_pp_params.py`，459003 的 338 条真实成绩）：`w=0.20` 时出现 2 处倒挂
  （18.60@99.85% 得分低于 17.50@100%，pp ×0.9617）；改为 `w=0.08`（±4%）后倒挂为 0。
- **成绩选择口径（PP 最大，而非分数最大）**：`/record?player=&chart=` 每谱返回 ≤20 条，
  **分数最高 ≠ PP 最高**（PP 由 accuracy / 无暇度 / 漏键驱动）。SuonasiOS 会把整段历史读下来再按规则选
  （其默认 `highestAccuracy`，另可选 `highestScore`/`latest`，见其 `lib/app_controller_scores.dart` 的
  `_selectedHistoryRecord` / `_compareHistoryRecords`）；我们取 **PP 最大**的那条，严格优于两者。
  实测（459003，442 张社区域谱）：按分数取 Best100 = 20085.1，按 ACC 取 = 20363.4，**按 PP 取 = 20371.9**
  （比旧口径 +286.8 PP，比按 ACC 取还 +8.5）；357 张里 **93 张**三者不一致，最大单张 +254.9。
  无定数时回退到 `best` 标记 / 最高分。实现：`phira_pp.pipeline._best_play_row`（单文件版对应 `bestRow()`）。
  校验：`scripts/verify_record_selection.py`。
- **Best-N 总 PP 的加权**：采用 osu! 的 `sum(pp_i * 0.95^i)`（最好一张全额，之后按 0.95 衰减），该形式来自 osu! 官方规则，非自拟。
- **覆盖统计必须展示**：`best` 走 `/record?player=&chart=` 逐谱请求（社区定数表 442 张），界面与 CLI 都要显示「扫描 N / 命中 M / 失败 K」，不得静默遗漏。
- **全量 Best100（CLI `best --all` / 网页「全量扫描」）**：覆盖 `division="regular"` 的全部 **9644**
  张谱（ranked 是其子集 583 张；troll/visual/plain/special/SP 由该筛选天然排除），
  逐谱 `?player=&chart=` 后难度按 ranked 定数 → 定数表 → **D\*** 取。
  实测（459003）：目录枚举并行翻页约 15s，逐谱 9644 条约 2–3 分钟，其中 456 张需算 D\*（首次要下载谱面包）。
  网页端为后台 job + 轮询进度（`POST /api/best100-full` 起、`GET ?job=` 查）。
- **D\* 必须限制在训练标签区间内**：模型是岭回归，标签区间 [0.0, 20.0]（n=749 缓存谱），
  区间外会**无界外推**——实测出现过 **−91.15 / +21.5**，配合 `diff_exp=6` 直接算出 1.5e7 的 pp。
  越界预测**一律排除并计入 `dstar_out_of_range`（不得钳到边界**：把垃圾 21.4 钳成 20.0 会把它塞进榜首）。
  判定统一走 `_dstar_usable()`：`chart()` / `best_plays_full` / 单文件构建共用同一条边界。
  **边界容差 `DSTAR_TOL = 0.05`**（= 模型 RMSE 0.686 的 7%）：只为放行**恰好压在标签上界**的数值噪声
  （#22206 = 20.0015，全库仅此 1 张落进容差带），真正的无界外推（41.31 / 21.5 / −91.15）依旧排除。
  实测（459003 全量，旧口径）：456 张需算 D*，其中 19 张越界被排除（`no_difficulty: 19`），最终 831 张可计分。
- **网页界面结构**：先显示独立登录页（`POST /api/login`，邮箱+密码仅本地转发、不回显不落盘，token 存 `data/.token`），
  登录后进入主界面：**上方 Best100、下方单个成绩查询**；`GET /api/session` 报告登录态、`POST /api/logout` 退出。
  两个功能都是**纯按钮**，Phira ID 取自登录会话（不再让用户输入），Best100 固定取前 100；只有单个查询需要输入谱面编号。
