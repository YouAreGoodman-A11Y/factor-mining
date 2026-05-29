# Factor Miner V2 (全自动因子挖掘系统) 实战手册

## 🎯 1. 系统本质
这是一个基于大语言模型（LLM）与 Qlib 向量化回测引擎的**端到端无人值守因子流水线**。
它的工作流是：**提出假说** (Proposer) → **写代码** (Builder) → **严苛回测** (The Backtester) → **法官审判** (Critic A&B) → **错题反思重写** (Refiner) → **录入黄金库**。

它的核心护城河是**“实盘级防坑”**：
- **拒绝“乌托邦回测”**：强制使用 T+1 日开盘买入、T+2 日开盘卖出，抗不过真实滑点和隔夜跳空的因子直接淘汰。
- **自动复权**：底层强制给所有价格字段挂载 `$adj_factor`，杜绝分红派息造成的“假动量”。
- **语法自愈**：大模型写错 Qlib 语法（如少传参数），系统会捕获报错并自动写入错题本（`syntax_pitfalls.md`），下次挖掘自动规避。

---

## 💻 2. 如何使用（CLI 启动指令）
系统的所有核心配置都暴露在了 `run_stable.py` 的命令行参数中。
最标准且安全的后台挂载跑法如下：

```bash
cd /root/.openclaw/workspace-data_engineer/factor_miner_v2 
nohup python run_stable.py --iterations 20 --market csi300 --strictness normal --model deepseek/deepseek-v4-pro > logs/run_current.log 2>&1 &
```

**核心参数说明：**
- `--iterations`：大模型的挖掘轮数（每轮生成 3 个因子，若失败最多自带 3 次内部修正循环）。
- `--market`：股票池。支持 `csi300`（大盘）、`csi500`、`csi1000`（小盘）、`all_a_shares`（全市场）。
- `--strictness`：及格线。
  - `relaxed`（宽松：IC>0.015即可）
  - `normal`（默认：要求 IC>0.025, 单调性>0.6, 换手率<0.6）
  - `strict`（严苛：IC>0.035）
- `--model`：指定底层大模型（如 `gemini/gemini-3.1-pro-preview` 或 `deepseek/deepseek-v4-pro`）。
- `--features` / `--operators`：可以强行限制大模型只能用哪些量价字段和算子（防止它写出太过玄幻的公式）。

---

## 🧭 3. 如何改变挖掘方向（定向挖矿）
如果你觉得它总是在挖“量价反转”，想让它去挖“长周期低波动”：
直接打开并编辑 `core/config.py` 文件，修改里面的 `TASK` 变量。
```python
# 例如改为：
TASK = "寻找中证1000中的中小盘低波动特征，关注20-60天的长周期动量，并严惩短期异动..."
```
改完后直接启动 `run_stable.py`，Proposer 就会按照你的新任务去构思。

---

## 📁 4. 挖掘结果去哪里看？
运行结束后（或运行中），去查看以下文件：
1. 🏆 **黄金因子库**：`pool/alpha_pool.json`。存活下来的好因子全在这里，包含详细的表达式、IC、夏普和多空年化。
2. 🗑️ **淘汰垃圾场**：`pool/rejected_pool.json`。因子是怎么死的（初筛死还是抢救无效死）都在这。
3. 📺 **实时日志**：`logs/run_xxx.log`。看大模型思考、报错、法官吵架的过程。
4. 🧠 **错题本**：`prompts/syntax_pitfalls.md`。系统的“免疫抗体”库。

> 💡 **防并发读写小贴士**：
> 如果需要进行多模型双盲对比（例如同时用 Gemini 和 DeepSeek 挖矿），请将整个 `factor_miner_v2` 文件夹 `cp -r` 复制为多个独立副本。这样能完美防止多个进程同时读写同一个 `pool.json` 导致的格式崩溃冲突。
