import re
"""Qlib factor evaluation with timeout protection."""

import signal, sys, gc
from core.config import TEST_TIMEOUT
import core.config as config
from core.llm import fix_qlib_expr


def _load_tester():
    """Lazy-load factor_evaluator (qlib init is heavy)."""
    sys.path.insert(0, "/root/.openclaw/workspace-data_engineer/factor_miner_x")
    from factor_evaluator import evaluate_factor
    return evaluate_factor


_evaluate_factor = None


def _get_ef():
    global _evaluate_factor
    if _evaluate_factor is None:
        _evaluate_factor = _load_tester()
    return _evaluate_factor


class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("Test timeout")


def run_test(expr: str, desc: str = "Auto") -> dict | None:
    """Evaluate a Qlib factor expression with timeout. Returns metrics dict or None."""
    expr_orig = expr
    expr = fix_qlib_expr(expr)
    if expr != expr_orig:
        print(f"   🔧 Fixed: {expr_orig[:50]}… → {expr[:50]}…", flush=True)

    # 1. 暴力拦截未来函数
    if re.search(r'Ref\([^,]+,\s*-\d+\)', expr):
        print(f"   ❌ Error: 检测到未来函数 (使用了负数窗口期: Ref(x, -N))", flush=True)
        return {"syntax_error": "Future data leakage detected: Do not use negative window in Ref(). Use positive window instead."}

    print(f"   🏃 Testing: {expr[:80]}…", flush=True)

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TEST_TIMEOUT)

    try:
        # 调用今天重写的、支持自动复权和 T+1 开盘滑点的终极引擎
        result = _get_ef()(
            expression=expr, description=desc,
            market=config.MARKET,
            start_time="2023-01-01", end_time="2023-12-31",
            despike=True, standardize=True, neutralize=True,
        )
        signal.alarm(0)
        
        if "error" in result:
            err_msg = result['error']
            print(f"   ❌ Error: {err_msg[:80]}", flush=True)
            return {"syntax_error": err_msg}
            
        # 提取新引擎的多维结果并映射回旧流水线需要的平铺 dict
        ic_res = result.get("ic_analysis", {}).get("rank", {})
        reb_res = result.get("rebalancing", {})
        qa_res = result.get("quantile_analysis", {})
        
        # 构建统一的 Metrics
        m = {
            "Rank_IC": float(ic_res.get("mean", 0)),
            "Rank_IC_IR": float(ic_res.get("ir", 0)),
            "Rank_IC_P_Value": float(ic_res.get("p_value", 1)),
            "Rank_IC_Positive_Rate": float(ic_res.get("positive_ratio", 0)),
            
            "Annual_Long_Short_Return": float(reb_res.get("long_short_annual_return", 0)),
            "Annual_Long_Short_Sharpe": float(reb_res.get("long_short_sharpe", 0)),
            
            "Monotonicity_Score": float(qa_res.get("monotonicity_score", 0)),
            "Top_Quantile_Daily_Turnover": float(reb_res.get("turnover", 1.0)),
        }
        
        # 兼容老 Critic 需要的 Q1~Q5 收益
        q_ann = qa_res.get("quantile_annual_returns", {})
        for q in q_ann:
            m[f"Ann_Ret_{q}"] = float(q_ann[q])
            
        rank_ic = m["Rank_IC"]
        ic_ir = m["Rank_IC_IR"]
        mono = m["Monotonicity_Score"]
        turn = m["Top_Quantile_Daily_Turnover"]
        print(f"   ✅ IC={rank_ic:.4f} IR={ic_ir:.4f} Mono={mono:.4f} Turn={turn:.4f}", flush=True)
        return m
    except TimeoutError:
        print(f"   ⏰ Timeout (> {TEST_TIMEOUT}s)", flush=True)
        return {"syntax_error": "Test timeout"}
    except Exception as e:
        signal.alarm(0)
        print(f"   ❌ Exception: {e}", flush=True)
        return {"syntax_error": str(e)}
    finally:
        gc.collect()
