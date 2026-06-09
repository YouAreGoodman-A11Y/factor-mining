#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
Factor Miner V2 - 全自动化因子挖掘系统启动脚本 (动态可调参 Python 版)
==============================================================================
"""

import os
import sys
import time
import subprocess
from datetime import datetime

# 1. 目标股票池 (支持 csi300, csi500, csi1000, all_a_shares)
MARKET = "csi300"

# 根据股票池自动切换工作目录与超时保护
if MARKET == "all_a_shares":
    WORK_DIR = "/root/.openclaw/workspace-data_engineer/factor_miner_v2_all_a_shares"
    TIMEOUT = 600
else:
    WORK_DIR = "/root/.openclaw/workspace-data_engineer/factor_miner_v2"
    TIMEOUT = 180

# 2. 回测时间窗口
START_TIME = "2023-12-31"
END_TIME = "2025-12-31"

# 3. 双模型组合引擎
PROPOSER = "gemini/gemini-3.1-pro-preview"
CODER = "deepseek/deepseek-v4-pro"

# 4. 回测及格线严格度 (relaxed / normal / strict)
STRICTNESS = "normal"

# 5. 挖掘轮数
ITERATIONS = 50

# 6. 底层容许使用的基础字段 (加入了刚刚探讨的 pct_chg)
FEATURES = "$close, $open, $high, $low, $amount, $volume, $pct_chg"

# 7. 挖掘定向任务配置 (发散式多样化任务)
TASK = (
    "Targeting the current market. 核心目标：在csi300中，寻找多样化的量价定价错误特征，建立丰富正交的因子库... "
    "请在这 5 个核心领域中自由穿梭、发散探索："
    "1) 【动量与趋势】不同时间窗的绝对/相对动量突破、动量惯性及加速度；"
    "2) 【量价微观结构】聪明钱动向、量价共振或背离、日内收益与隔夜收益的博弈异常；"
    "3) 【波动率与偏度】高/低波动率溢价、收益率偏度特征与长尾风险特征；"
    "4) 【均值回归】极端恐慌/贪婪后的过度反应修复与均值回归；"
    "5) 【流动性与换手】换手率突跳特征、非流动性补偿与资金沉淀信号。"
    "鼓励创造性地嵌套时间序列操作(Mean, Std, Delta)与横截面操作(Rank)以消除大盘共性波动。"
    "You must rely on past price (high, low, open, close), volume/amount, and pct_chg data. "
    "NOTE: Do NOT use $vwap. To calculate VWAP, you MUST use Div(Div($amount, Add($volume, 1e-8)), $adj_factor). "
    "Focus on generating highly predictive factors with strong structural logic and mathematical soundness."
)

# 8. 运行模式 (True: 前台直接打印日志; False: 后台挂载)
CONSOLE_MODE = False

# ==============================================================================
# 启动执行逻辑
# ==============================================================================
def main():
    print(f">>> 正在切换到工作目录: {WORK_DIR}")
    if not os.path.exists(WORK_DIR):
        print(f"❌ 错误: 工作目录 {WORK_DIR} 不存在!")
        sys.exit(1)
        
    os.chdir(WORK_DIR)
    
    # 注入 API Key
    os.environ["GEMINI_API_KEY"] = "AIzaSyCZJVJ0wa3FUXx2QNCpCB8k0-Ltjj7A0Q4"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/run_{MARKET}_{timestamp}.log"
    
    # 构建执行参数
    cmd = [
        "python3", "run_stable.py",
        "--task", TASK,
        "--start_time", START_TIME,
        "--end_time", END_TIME,
        "--market", MARKET,
        "--model_proposer", PROPOSER,
        "--model_coder", CODER,
        "--strictness", STRICTNESS,
        "--iterations", str(ITERATIONS),
        "--timeout", str(TIMEOUT),
        "--features", FEATURES
    ]
    
    print("=====================================================")
    print(f"🚀 即将启动 Factor Miner V2")
    print(f"📂 工作区   : {WORK_DIR}")
    print(f"📈 股票池   : {MARKET}")
    print(f"⏱️  回测周期 : {START_TIME} 到 {END_TIME}")
    print(f"🤖 模型组合 : {PROPOSER} (Proposer) + {CODER} (Coder)")
    print("=====================================================")
    
    if CONSOLE_MODE:
        print(">>> [前台模式] 3秒后正式起飞，按 Ctrl+C 可随时终止...\n")
        time.sleep(3)
        cmd.append("--console")
        try:
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            print("\n⏹️ 已手动终止挖掘任务。")
    else:
        print(f">>> [后台模式] 正在挂载启动 Factor Miner V2...")
        cmd_str = " ".join([f'"{c}"' if " " in c else c for c in cmd])
        full_cmd = f"nohup {cmd_str} > {log_file} 2>&1 & echo $! > run_stable.pid"
        
        proc = subprocess.Popen(full_cmd, shell=True, preexec_fn=os.setsid)
        print("✅ 因子挖掘引擎已成功挂载！")
        print(f"📂 实时日志 : {WORK_DIR}/{log_file}")
        print("💡 提示: 您可以使用以下命令查看实时进度：")
        print(f"tail -f {WORK_DIR}/{log_file}")

if __name__ == "__main__":
    main()