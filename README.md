# Factor Miner V2 终极操作手册

这是一个基于大语言模型（LLM）与 Qlib 向量化回测引擎的**全自动量化因子挖掘流水线**。
它实现了从“提出假说 → 构建因子 → 严苛回测 → 法官审判 → 自我纠错迭代 → 录入因子库”的端到端无人值守运行，并完全对齐了实盘的滑点与复权逻辑。

---

## 一、如何启动挖掘 (CLI 参数详解)

你可以在 `/root/.openclaw/workspace-data_engineer/factor_miner_v2` 目录下，直接使用 `python run_stable.py` 启动挖掘。所有核心环境配置均已开放为命令行参数。

### 1. 基础启动 (指定轮数与股票池)
```bash
python run_stable.py --iterations 5 --market "csi300"
```
*   `--iterations`：大模型尝试的完整循环轮数（每轮都会产生 3 个因子变体并进行一波 Refine 抢救）。
*   `--market`：底层 Qlib 切分的股票池。支持 `all_a_shares` (全市场), `csi300` (大盘), `csi500`, `csi1000` (小盘) 等。不同市场池里的量价规律截然不同（比如大盘缩量多反转，小盘可能是锁仓）。

### 2. 精细控制 (限制特征与算子)
为了防止大模型过度拟合或者写出极其复杂、不具备金融学意义的怪物公式，你可以人为约束它的工具箱。
```bash
python run_stable.py --iterations 10 --market "csi1000" \
  --features "\$close, \$open, \$high, \$low, \$volume, \$vwap" \
  --operators "Delta(x,N), Mean(x,N), Std(x,N), Rank(x,N), Ref(x,N), Corr(x,y,N), Sum(x,N), Abs(x), +, -, *, /, If(cond,A,B), And, Or"
```
*   `--features`：告诉大模型当前只能用哪些基础量价字段（例如如果你不想让它用价格，只留 `$volume`，它就会被迫去挖纯量因子）。
*   `--operators`：告诉大模型可以使用的 Qlib 算子库。

### 3. 法官标准 (Strictness)
```bash
python run_stable.py --strictness "relaxed" 
```
*   `--strictness`：可选 `relaxed`, `normal` (默认), `strict`。它决定了因子入库的及格线。比如 `relaxed` 允许 Rank IC > 0.015 即可及格，而 `strict` 则要求 IC 必须 > 0.035。

---

## 二、如何改变挖掘的方向 (Task 目标设定)

如果你想让矿工停止寻找当前的“量价反转”特征，转而去寻找“长周期低波动”，你需要修改 `core/config.py` 中的 `TASK` 全局变量。

```python
# 在 core/config.py 中修改 TASK：
TASK = (
    "A mean-reversion and volatility-adjusted momentum effect targeting mid/small-cap stocks in CSI1000. "
    "Focus on finding stable mid-to-long term momentum (e.g., 20 to 60 days) penalized by short-term spikes..."
)
```
修改完成后，直接启动 `run_stable.py`，Proposer（假说提出者）就会根据你的新任务指引去构思公式。

---

## 三、流水线的核心防线与机制

### 1. 实盘级防穿越与滑点对齐（The Backtester）
- **自动除权除息**：系统会自动抓取表达式里的 `$close` 等字段，在底层计算前替换为 `($close * $adj_factor)`，根绝由于分红送配导致的伪动量暴涨暴跌。
- **隔夜跳空猎杀**：传统的 Qlib 回测往往是“T日收盘到T+1日收盘”，这会把 T+1 日开盘的巨大跳空红利算进利润。本引擎已强制改为 **T+1 日开盘买入，T+2 日开盘卖出**。只有能在次日开盘实盘成交且依然能赚钱的因子，才能活着走出来。

### 2. 双轨法官机制（Critic A & B）
- **严父 (Critic A)**：绝对理性的数字判官。如果因子的 P 值 > 0.05（统计不显著，像掷硬币）、胜率极度逼近 50%、或者日换手率 > 0.60，严父会直接亮红牌并指出致死原因。
- **慈母 (Critic B)**：发现美的眼睛。如果一个因子的绝对 IC 不够高，但它有着**完美的阶梯分层单调性（>0.8）**、**极高的多空年化（>10%）**或者**极低的换手率**，慈母会将它送入打捞通道（Refine Pipeline）。

### 3. 错题本自愈系统（Auto-Prompt & Syntax Pitfalls）
- 大模型经常会在 Qlib 独有的语法上翻车（比如 `Rank` 忘了写窗口大小，或者给横截面算子乱加负号）。
- 本系统配备了**语法错误隔离池 (`pool/syntax_errors.jsonl`)**。一旦引擎执行失败，不会将其算作逻辑淘汰，而是捕获报错。
- 如果发生新的语法错误，系统会自动唤醒大模型进行分析，并将防坑法则**自动写入** `prompts/syntax_pitfalls.md`。下一次大模型再写代码时，就会先阅读这本带着“血泪教训”的错题本，从而实现系统的自我进化与免疫。

---

## 四、挖掘结果去哪里看？

1. **🏆 黄金因子库**：`pool/alpha_pool.json`。所有通过了严苛法官审判、且能在实盘滑点中存活的因子，都会连同其多空年化、夏普、IC 曲线等数据保存在此。
2. **🗑️ 淘汰垃圾场**：`pool/rejected_pool.json`。记录了因子阵亡的阶段（是在初筛被杀，还是在 Refine 抢救无效）。
3. **📺 实时监控日志**：`logs/` 目录下。文件名会标注对应的测试市场，例如 `run_csi1000_20260521_172046.log`。你可以使用 `tail -f logs/xxx.log`，像看电影一样观看大模型“构思 → 碰壁报错 → 法官辱骂 → 医生诊断反思 → 再次重写 → 成功入库”的全过程。
4. **🧠 错题本**：`prompts/syntax_pitfalls.md`。包含了系统自动积累或你手动加入的 Qlib 代码避坑经验。