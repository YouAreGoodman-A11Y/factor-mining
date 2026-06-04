"""Global configuration for factor_miner_x."""

import os

# Task is dynamically formulated now, but we keep a base structure
TASK_TEMPLATE = (
    "Targeting the {market} market. 核心目标：寻找多样化的量价定价错误特征，建立丰富正交的因子库。"
    "请在这 5 个核心领域中自由穿梭、发散探索："
    "1) 【动量与趋势】不同时间窗的绝对/相对动量突破、动量惯性及加速度；"
    "2) 【量价微观结构】聪明钱动向、量价共振或背离、日内收益与隔夜收益的博弈异常；"
    "3) 【波动率与偏度】高/低波动率溢价、收益率偏度特征与长尾风险特征；"
    "4) 【均值回归】极端恐慌/贪婪后的过度反应修复与均值回归；"
    "5) 【流动性与换手】换手率突跳特征、非流动性补偿与资金沉淀信号。"
    "鼓励创造性地嵌套时间序列操作(Mean, Std, Delta)与横截面操作(Rank)以消除大盘共性波动。"
    "You must rely on past price (high, low, open, close) and volume/amount data. "
    "NOTE: Do NOT use $vwap. To calculate VWAP, you MUST use Div(Div($amount, Add($volume, 1e-8)), $adj_factor). "
    "Focus on generating highly predictive factors with strong structural logic and mathematical soundness."
)
TASK = TASK_TEMPLATE.format(market="current")  # Fallback

MODEL_PROPOSER = "gemini/gemini-3.1-pro-preview"
MODEL_CODER = "deepseek/deepseek-v4-pro"
MODEL = "deepseek/deepseek-v4-pro"  # Fallback
TEST_TIMEOUT = 600  # seconds per evaluate_factor call

# Dynamic Context Configuration (Can be overridden by CLI args)
MARKET = "all_a_shares"
FEATURES = "$close, $open, $high, $low, $amount, $volume"
OPERATORS = "ANY valid Qlib mathematical or timeseries operator (e.g., Delta, Mean, Std, Sum, Max, Min, Rank, Ref, Corr, Abs, Sign, Power, Log, EMA, MACD, RSI, WMA, etc., plus basic arithmetic +, -, *, / and If(cond, A, B)). You are free to invent complex Qlib expressions as long as they follow strict Qlib syntax."

STRICTNESS = {
    "relaxed": {"min_ic": 0.015, "min_ic_ir": 0.12, "min_mono": 0.40},
    "normal":  {"min_ic": 0.025, "min_ic_ir": 0.20, "min_mono": 0.60},
    "strict":  {"min_ic": 0.035, "min_ic_ir": 0.30, "min_mono": 0.80},
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL_DIR = os.path.join(BASE_DIR, "pool")
LOG_DIR = os.path.join(BASE_DIR, "logs")
TESTER_DIR = os.path.join(BASE_DIR, "..", "factor_miner")

os.makedirs(POOL_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

START_TIME = "2023-01-01"
END_TIME = "2025-12-31"
