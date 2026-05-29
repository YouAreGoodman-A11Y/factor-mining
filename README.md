# 🚀 Factor Miner V2 - 自动化量化因子挖掘流水线

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Qlib](https://img.shields.io/badge/Qlib-Supported-brightgreen)](https://github.com/microsoft/qlib)
[![LLM Agent](https://img.shields.io/badge/Agent-Autonomous-orange)](#)
[![Status](https://img.shields.io/badge/Status-Production_Ready-success)](#)

这是一个基于大语言模型（LLM）与 Qlib 向量化回测引擎的**全自动量化因子挖掘流水线**。实现了从“提出假说 → 构建因子 → 严苛回测 → 法官审判 → 自我纠错迭代 → 录入因子库”的端到端无人值守运行，并完全对齐了实盘的滑点与复权逻辑。

---

## 📑 目录
- [架构概览](#-架构概览)
- [核心防线与机制](#-核心防线与机制)
- [快速开始](#-快速开始)
- [目录结构](#-目录结构)
- [挖掘结果与监控](#-挖掘结果与监控)

---

## 🧠 架构概览

Factor Miner V2 不仅仅是一个代码生成器，而是一个**多智能体（Multi-Agent）协作的投研团队**：
1. **Proposer (研究员)**：根据设定的宏观/微观 Task，提出具有金融逻辑的因子假说，并编写 Qlib 表达式。
2. **Backtester (回测引擎)**：无情的数据机器，加载底层高频/日度数据，在实盘滑点约束下进行清洗与回测。
3. **Critic (法官与慈母)**：双轨评估机制，既严查统计显著性与换手率（防止过拟合与高摩擦），又善于发现单调性极佳但 IC 偏低的潜力因子。
4. **Refiner (抢救医生)**：针对法官提出的修改意见，对潜力因子进行公式重构与抢救。

---

## 🛡️ 核心防线与机制

### 1. 实盘级防穿越与滑点对齐
- **自动复权**：自动挂载 `$adj_factor` 进行除权除息，彻底根除因分红送配导致的伪动量暴涨暴跌陷阱。
- **隔夜跳空猎杀**：强制修正传统 Qlib 回测的 T+1 理想收益，改为 **T+1 日开盘买入，T+2 日开盘卖出**。只有能承受真实开盘冲击成本的因子才能存活。

### 2. 双轨法官机制 (Dual-Critic System)
- **严父 (Critic A)**：绝对理性的数字判官。一旦因子的 P 值 > 0.05（统计不显著）、胜率逼近 50% 或日换手率过高（>0.60），直接红牌淘汰。
- **慈母 (Critic B)**：挖掘潜力股。如果因子绝对 IC 不高，但拥有**极佳的阶梯分层单调性（>0.8）**、高多空年化（>10%）或极低换手率，将送入 Refine Pipeline 进行打捞。

### 3. 错题本自愈系统 (Self-Healing)
配备独立的**语法错误隔离池 (`pool/syntax_errors.jsonl`)**。遇到未知的 Qlib 语法报错，系统会自动唤醒大模型进行反思，并将防坑法则自动写入 `prompts/syntax_pitfalls.md`。实现系统的自我进化与免疫。

---

## ⚡ 快速开始

在终端进入项目根目录，使用 `run_stable.py` 启动挖掘。所有核心环境配置均已开放为命令行参数。

### 基础启动
指定迭代轮数与底层股票池（如全市场 `all_a_shares`，大盘 `csi300`，小盘 `csi1000`）。
```bash
python run_stable.py --iterations 5 --market "csi300"
```

### 精细控制 (特征与算子约束)
防止模型写出无实际金融意义的怪物公式，可人为约束工具箱：
```bash
python run_stable.py --iterations 10 --market "csi1000" \
  --features "\$close, \$open, \$high, \$low, \$volume, \$vwap" \
  --operators "Delta(x,N), Mean(x,N), Std(x,N), Rank(x,N), Ref(x,N), Corr(x,y,N), Sum(x,N), Abs(x), +, -, *, /, If(cond,A,B), And, Or"
```

### 调整法官严苛度
```bash
python run_stable.py --strictness "relaxed" # 可选: relaxed, normal, strict
```

> 💡 **如何改变挖掘方向？**
> 修改 `core/config.py` 中的 `TASK` 全局变量，为其设定新的宏观或微观目标（如：寻找长周期低波动因子），Proposer 会自动根据新指引工作。

---

## 📂 目录结构

```text
factor_miner_v2/
├── run_stable.py             # 🚀 主启动入口脚本
├── factor_evaluator.py       # 核心回测与评估逻辑
├── test_evaluator.py         # 评估器单元测试
├── core/                     # 核心组件库
│   ├── config.py             # 全局配置 (Task目标设定)
│   ├── llm.py                # 大模型 API 交互封装
│   ├── pipeline.py           # 挖掘流水线主控逻辑
│   ├── pool.py               # 因子池管理器
│   └── tester.py             # 异常与测试处理器
├── pool/                     # 🗄️ 因子库与状态存储
│   ├── alpha_pool.json       # [🏆] 存活的黄金因子库
│   ├── rejected_pool.json    # [🗑️] 淘汰的垃圾场
│   ├── syntax_errors.jsonl   # 语法错误日志
│   └── evo_trace.json        # 进化轨迹追踪
├── prompts/                  # 🧠 大模型提示词工程
│   ├── factor_refine_guide.md # Refiner 抢救指南
│   └── syntax_pitfalls.md    # [动态更新] 语法错题本防坑指南
└── logs/                     # 📺 实时监控日志存放区
```

---

## 📈 挖掘结果与监控

1. **🏆 黄金因子库**：查看 `pool/alpha_pool.json`。通过审判的因子连同其多空年化、夏普、IC 曲线数据均保存在此。
2. **📺 实时监控**：新开终端使用 `tail -f logs/<log_name>.log`，即可像看电影一样观看大模型“构思 → 报错 → 反思 → 重构 → 入库”的完整推演过程。
