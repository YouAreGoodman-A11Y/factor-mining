"""Global configuration for factor_miner_x."""

import os

# Task is dynamically formulated now, but we keep a base structure
TASK_TEMPLATE = (
    "Targeting the {market} market. Use any behavioral finance, economic theory, or statistical principles "
    "you can think of to find novel factors that can explain next-day returns. "
    "You must rely on past price (high, low, open, close) and volume/amount data. "
    "NOTE: Do NOT use $vwap. To calculate VWAP, you MUST use Div(Div($amount, Add($volume, 1e-8)), $adj_factor). "
    "Focus on generating highly predictive factors with strong structural logic and mathematical soundness."
)
TASK = TASK_TEMPLATE.format(market="current")  # Fallback

MODEL = "deepseek/deepseek-v4-pro"
TEST_TIMEOUT = 180  # seconds per evaluate_factor call

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
