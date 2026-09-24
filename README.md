# Phira PP

Phira 的 PP（表现点）计算器：自研客观难度 **D\*** + PP 公式 + 本地网页 / 命令行 / 单文件网页三种用法。

> 本仓库是**私有**项目。Phira 成绩接口的做法是逆向所得（见 `.trae/rules/project_rules.md`），
> 仓库内**不含**任何谱面包，也不含任何账号凭据。

---

## 快速开始

### 1. 网页界面（推荐）

```powershell
.\start.bat
```

会自动打开 `http://127.0.0.1:8000/`。先显示登录页（邮箱 + 密码**仅本地转发、不回显、不落盘**，
token 存 `data/.token`），登录后进入主界面：**上方 Best100、下方单个成绩查询**。
关闭服务：在该窗口输入 `off` 并回车。

> ⚠️ 必须经 `http://127.0.0.1:8000/` 访问。直接双击 `web/index.html` 时所有 `/api/*` 都会失败。

### 2. 命令行

```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\pp.py chart 54540
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\pp.py best  <Phira ID> -n 100
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\pp.py best  <Phira ID> --all   # 全量扫描 9644 张
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\pp.py play  <Phira ID> <谱面 ID>
```

### 3. 单文件版（给没有 Python 的人用）

根目录 `PhiraPP.html` 双击即可：浏览器**直连** Phira API，无需服务端。
由 `scripts/build_standalone.py` 生成（把社区定数表 + 专家覆盖值烘进 HTML）。

**硬限制**：浏览器算不了自研 `D*`（需要 Python 解析谱面包 + 模型），
所以单文件只支持 **ranked 谱**与**社区定数谱**；其它谱会明确提示而不是猜。

---

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt      # requests / numpy / scipy
```

> 必须用项目内的 `.venv`。系统 PATH 上的 `python` 是损坏的 Microsoft Store stub。

---

## 难度取值（按优先级）

| 优先级 | 条件 | 采用值 |
|---|---|---|
| 0 | `data/difficulty_override.json` 里显式列出 | **专家覆盖**（唯一允许故意偏离模型的地方） |
| 1 | `ranked` 谱 | 谱师定数 |
| 2 | 在 Suonasi KV 定数表（`data/kv_diff.json`） | 社区定数 (Suonasi) |
| 3 | 在主观定数表（`data/subjective_diff.xlsx`） | 社区定数 (主观)，且**只作下限**（D\* 更高时取 D\*） |
| 4 | 其余 | **D\* 模型**；预测落到 `[0, 20]`（±0.05 容差）之外则**剔除并计数** |

## PP 公式

```
单曲 PP = base · D^6 · acc_factor · precision_factor · error_factor
  base = 1000 / 18^6
  acc_factor       = ((acc − 0.70) / 0.30)^4
  precision_factor = 1 + 0.08 · (score − 0.5)        # 无暇度，幅度仅 ±4%
  error_factor     = (1 − (bad + miss) / 总键数)^3
总 PP = Σ(i=1..100) PP_i · 0.95^(i−1)                 # osu! 官方加权
```

同一谱面有多条成绩时取 **PP 最高**的那条（不是分数最高）。

## D\*（客观难度）

对谱面特征做**岭回归**（α=30 固定）拟合定数，共 **19 个特征**（含"最难 10s 窗"分段聚合、
四指可达性、物量饱和项），并有两道**输入护栏**：特征裁剪到训练区间 + 密度上限。
完整公式、每个特征的权重/均值/标准差、以及全部实测指标见 **[docs/formula.md](docs/formula.md)**。

当前精度：CV R² **0.859**、嵌套 CV **0.854**、in-sample RMSE **0.606**（949 张训练谱）。

---

## 目录

```
phira_pp/           核心库（api 客户端、谱面解析、特征、D*、PP、流水线、网页后端）
scripts/            命令行入口 + 全部实验/校验脚本（见下）
web/                本地网页（index.html）+ 单文件模板
data/               模型、定数表、特征缓存（谱面包 data/packages/ 不入库，约 7.8 GB）
docs/formula.md     公式总览（改动模型后必须同步）
PhiraPP.html        单文件版（由 build_standalone.py 生成）
```

## 复现与校验

```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\reextract_features.py          # 离线重算特征
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\fit_difficulty2.py             # 重训并落盘模型
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\verify_formula_doc.py          # 文档 vs 源码逐值核对
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\verify_subjective.py           # 定数表/覆盖层断言
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe scripts\verify_record_selection.py     # 成绩选择口径
node scripts/verify_standalone.mjs <Phira ID>                                          # 单文件 vs CLI 对拍
```

## 数据来源与致谢

- 成绩查询：Phira 公开接口（`/record?player=&chart=`，**无需 token**）。
- 社区定数表：SuonasiOS 的 KV 服务；成绩选择口径亦参考其实现。
- 主观定数表：项目主提供的 xlsx。
- 参考方案：PPSR（用作差距审计的对照，见 `.trae/rules/project_rules.md`）。

## 已知限制

- 高难端（18+）的谱师定数样本极少，系统性偏差主要靠主观定数表 + 专家覆盖层修正。
- D\* 只对**人类可达**的范围可信；越界预测一律剔除而非钳到边界。
- 单文件版无法计算 D\*（见上）。
