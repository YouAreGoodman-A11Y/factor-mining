import os, sys, json, warnings
import numpy as np
import pandas as pd
import scipy.stats as stats
import qlib
from qlib.data import D

warnings.filterwarnings("ignore")

_QLIB_INITED = False

def _ensure_qlib():
    global _QLIB_INITED
    if not _QLIB_INITED:
        qlib.init(provider_uri="/data/mamba_qlib_bin", region=qlib.config.REG_CN)
        _QLIB_INITED = True

def _convert_numpy(obj):
    if isinstance(obj, dict):
        return {k: _convert_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_numpy(v) for v in obj]
    elif hasattr(obj, "item"):
        return obj.item()
    return obj

def _despike_mad(s: pd.Series) -> pd.Series:
    med = s.median()
    mad = (s - med).abs().median() * 1.4826
    return s.clip(med - 3 * mad, med + 3 * mad)

def evaluate_factor(
    expression: str,
    description: str = "",
    market: str = "all_a_shares",
    start_time: str = "2023-01-01",
    end_time: str = "2023-12-31",
    forward_days: int = 1,
    despike: bool = True,
    standardize: bool = True,
    neutralize: bool = False,
    n_quantiles: int = 5,
) -> dict:
    """全流程因子评价。"""
    _ensure_qlib()

    # 自动替换因子表达式中的基础量价字段，将其转为复权价
    auto_adj_expr = expression
    for field in ["$close", "$open", "$high", "$low"]:
        # 使用 Qlib 语法将其自动替换为乘以复权因子的逻辑
        auto_adj_expr = auto_adj_expr.replace(field, f"({field} * $adj_factor)")
    # Note: $amount 和 $volume 代表的是实际成交额和成交量，不需要也不应该复权。
        
    if auto_adj_expr != expression:
        print(f"Info: 自动复权:\n  [原] {expression[:100]}...\n  [新] {auto_adj_expr[:100]}...", flush=True)
        pass

    # ── 1. 提取数据 ──
    # 修改预测未来的 Label：严格模拟实盘滑点，使用 T+1日开盘买入，T+1+forward_days日开盘卖出
    # 例如 forward_days=1 时：(T+2开盘价 * T+2复权因子) / (T+1开盘价 * T+1复权因子) - 1
    label_expr = f"(Ref($open, -{forward_days+1}) * Ref($adj_factor, -{forward_days+1})) / (Ref($open, -1) * Ref($adj_factor, -1)) - 1"
    # 严格对齐米筐的默认过滤：剔除 ST，剔除无成交量，剔除上市不满 180 个交易日的新股
    filter_expr = "And(Count($close, 180) >= 180, And($volume > 0, $is_st == 0))"
    
    # 获取真实 IC 衰减数据 (改用 Pandas shift 加速)
    decay_days = [1, 2, 3, 4, 5, 10, 20]
    
    fields = [auto_adj_expr, label_expr, filter_expr, "$close", "$open", "$up_limit", "$down_limit", "$adj_factor"]
    col_names = ["factor", "label", "is_valid", "close", "open", "up_limit", "down_limit", "adj_factor"]
    
    if neutralize:
        fields.append("$total_mv_z1")
        col_names.append("mcap")

    # print("Step 1: Extracting data...", flush=True)
    try:
        df = D.features(
            D.instruments(market=market),
            fields=fields,
            start_time=start_time,
            end_time=end_time,
            freq="day",
        )
    except Exception as e:
        return {"error": f"数据提取失败: {e}"}
    # print("Step 1 done. DF shape:", df.shape, flush=True)

    df.columns = col_names
    # print("Step 2: Cleaning data & Computing Decay Labels...", flush=True)
    
    # 修复：必须在剔除无效行和空值之前，保持时间序列完整连续的情况下进行 shift
    decay_cols = []
    # 提前算出开盘复权价序列，加速 shift 计算，用于计算信息衰减
    df["adj_open_price"] = df["open"] * df["adj_factor"]
    for d in decay_days:
        col = f"ret_fwd_{d}"
        decay_cols.append(col)
        # 对应的衰减也要换成从 T+1日开盘 到 T+1+d日开盘的收益率
        df[col] = df.groupby(level="instrument")["adj_open_price"].shift(-(d+1)) / df.groupby(level="instrument")["adj_open_price"].shift(-1) - 1

    # 在计算完未来的收益率后，再安全地剔除无效行
    df = df[df["is_valid"] == 1].drop(columns=["is_valid"])
    df = df.dropna(subset=["factor"])
    if df.empty:
        return {"error": "无有效数据"}

    # 回测用的涨跌停过滤：简化保留原有逻辑（T日过滤）
    df = df[df["close"] < df["up_limit"] - 0.001]
    df = df[df["close"] > df["down_limit"] + 0.001]
    df = df.drop(columns=["close", "open", "up_limit", "down_limit", "adj_factor", "adj_open_price"])

    if despike:
        # print("Step 3: Despiking...", flush=True)
        med = df.groupby(level="datetime")["factor"].transform("median")
        mad = (df["factor"] - med).abs().groupby(level="datetime").transform("median") * 1.4826
        df["factor"] = df["factor"].clip(med - 3 * mad, med + 3 * mad)
        
    if standardize:
        # print("Step 4: Standardizing...", flush=True)
        mean = df.groupby(level="datetime")["factor"].transform("mean")
        std = df.groupby(level="datetime")["factor"].transform("std")
        # 避免除以 0
        std = std.replace(0, 1)
        df["factor"] = (df["factor"] - mean) / std

    if neutralize:
        # print("Step 5: Neutralizing...", flush=True)
        import statsmodels.api as sm
        def _neutralize(g):
            valid = g.dropna(subset=["factor", "mcap"])
            if len(valid) < 5:
                return g["factor"]
            y = valid["factor"].astype(float)
            x = sm.add_constant(np.log(valid["mcap"].astype(float) + 1))
            g.loc[valid.index, "factor"] = sm.OLS(y, x).fit().resid.astype(np.float32)
            return g["factor"]
        df["factor"] = df.groupby(level="datetime", group_keys=False).apply(_neutralize)
        if standardize:
            df["factor"] = df.groupby(level="datetime", group_keys=False)["factor"].apply(
                lambda s: (s - s.mean()) / s.std() if s.std() > 0 else s - s.mean()
            )

    df = df.dropna(subset=["factor", "label"])
    total_days = len(df.index.get_level_values("datetime").unique())
    all_dates = sorted(df.index.get_level_values("datetime").unique())

    # print("Step 6: IC Analysis...", flush=True)
    # ── 2. IC 分析 ──
    ic_dates = all_dates if forward_days == 1 else all_dates[::forward_days]
    ic_dates = [d for d in ic_dates if d < all_dates[-1]]

    pearson_ics, rank_ics = [], []
    real_ic_decay = {d: [] for d in decay_days}

    for dt in ic_dates:
        day = df.xs(dt, level="datetime").dropna(subset=["factor", "label"])
        # 修正 NaN 污染：跳过方差为 0 的异常日
        if len(day) < 10 or day["factor"].std() <= 1e-8 or day["label"].std() <= 1e-8:
            continue
            
        p_ic, _ = stats.pearsonr(day["factor"], day["label"])
        r_ic, _ = stats.spearmanr(day["factor"], day["label"])
        pearson_ics.append(p_ic)
        rank_ics.append(r_ic)

        # 计算真实 IC 衰减
        for d, col in zip(decay_days, decay_cols):
            day_d = df.xs(dt, level="datetime").dropna(subset=["factor", col])
            if len(day_d) >= 10 and day_d["factor"].std() > 1e-8 and day_d[col].std() > 1e-8:
                d_ic, _ = stats.spearmanr(day_d["factor"], day_d[col])
                real_ic_decay[d].append(d_ic)

    p_ic_s, r_ic_s = pd.Series(pearson_ics), pd.Series(rank_ics)

    def _ic_stats(s):
        mean = float(s.mean()) if len(s) > 0 else 0.0
        std = float(s.std()) if len(s) > 1 else 0.0
        ir = mean / std if std > 0 else 0.0
        t = np.sqrt(len(s)) * mean / std if std > 0 else 0.0
        p = 2 * (1 - stats.t.cdf(abs(t), df=len(s) - 1)) if len(s) > 1 else 1.0
        return {
            "mean": round(mean, 6), "std": round(std, 6),
            "ir": round(ir, 6), "t_stat": round(t, 4),
            "p_value": round(p, 6), "significant_5pct": bool(p < 0.05),
            "positive_ratio": round((s > 0).sum() / len(s), 4) if len(s) > 0 else 0.0, 
            "n_days": len(s),
        }

    ic_result = {
        "pearson": _ic_stats(p_ic_s),
        "rank": _ic_stats(r_ic_s),
        "ic_type": "non_overlapping" if forward_days > 1 else "daily",
    }

    # print("Step 7: Rebalancing...", flush=True)
    # ── 3. 真实调仓回测 ──
    reb_dates = all_dates[::forward_days]
    reb_sell_dates = []
    for d in reb_dates:
        idx = all_dates.index(d)
        sell_idx = min(idx + forward_days, len(all_dates) - 1)
        if sell_idx == idx:
            continue
        reb_sell_dates.append((d, all_dates[sell_idx]))

    if len(reb_sell_dates) < 2:
        return {"error": "调仓期数不足", **ic_result}

    ls_period_returns = []
    top_period_returns = []
    bot_period_returns = []
    q_ret_accum = {f"Q{q}": [] for q in range(1, n_quantiles + 1)}
    prev_top_set = None
    turnover_list = []

    for rd, sd in reb_sell_dates:
        reb_data = df.xs(rd, level="datetime").copy()
        reb_data = reb_data[["factor"]].dropna()
        if len(reb_data) < n_quantiles + 1:
            continue

        noise = np.random.normal(0, 1e-8, size=len(reb_data))
        try:
            reb_data["q"] = n_quantiles - pd.qcut(reb_data["factor"] + noise, n_quantiles, labels=False, duplicates="drop")
        except Exception:
            continue

        sell_df = df.xs(rd, level="datetime")[["label"]].rename(columns={"label": "ret_future"}).dropna()
        merged = reb_data.join(sell_df[["ret_future"]], how="inner")
        merged = merged.dropna(subset=["ret_future"])
        if len(merged) < n_quantiles + 1:
            continue

        for q in range(1, n_quantiles + 1):
            qr = merged.loc[merged["q"] == q, "ret_future"].mean()
            q_ret_accum[f"Q{q}"].append(qr)

        top_ret = merged.loc[merged["q"] == 1, "ret_future"].mean()
        bot_ret = merged.loc[merged["q"] == n_quantiles, "ret_future"].mean()

        cur_top = set(merged[merged["q"] == 1].index)
        if prev_top_set is not None and len(prev_top_set) > 0:
            to = 1 - len(cur_top & prev_top_set) / max(len(prev_top_set), 1)
            turnover_list.append(to)
        prev_top_set = cur_top

        top_period_returns.append(top_ret)
        bot_period_returns.append(bot_ret)
        ls_period_returns.append(top_ret - bot_ret)

    if len(ls_period_returns) < 2:
        return {"error": "调仓期数据不足", **ic_result}

    # 多空收益 = Q1(因子最高)做多 - Q5(因子最低)做空，永远不做符号翻转
    ls_arr = np.array(ls_period_returns)
    top_arr = np.array(top_period_returns)
    bot_arr = np.array(bot_period_returns)

    ann_factor = 252 / forward_days
    ann_ls = ls_arr.mean() * ann_factor
    ann_top = top_arr.mean() * ann_factor
    ann_bot = bot_arr.mean() * ann_factor
    ann_ls_std = ls_arr.std() * np.sqrt(ann_factor)
    ls_sharpe = ann_ls / ann_ls_std if ann_ls_std > 0 else 0
    ls_win_rate = (ls_arr > 0).sum() / len(ls_arr)
    avg_turnover = float(np.mean(turnover_list)) if turnover_list else 0

    if len(ls_arr) > 1:
        ls_t, _ = stats.ttest_1samp(ls_arr, 0)
        ls_p = 2 * (1 - stats.t.cdf(abs(ls_t), df=len(ls_arr) - 1))
    else:
        ls_t, ls_p = 0, 1

    reb_result = {
        "rebalancing_periods": len(ls_period_returns),
        "top_annual_return": round(ann_top, 6),
        "bottom_annual_return": round(ann_bot, 6),
        "long_short_annual_return": round(ann_ls, 6),
        "long_short_annual_std": round(ann_ls_std, 6),
        "long_short_sharpe": round(ls_sharpe, 4),
        "long_short_win_rate": round(ls_win_rate, 4),
        "long_short_t_stat": round(ls_t, 4),
        "long_short_p_value": round(ls_p, 6),
        "long_short_significant": bool(ls_p < 0.05),
        "avg_holding_period_return": round(float(ls_arr.mean()), 8),
        "turnover": round(avg_turnover, 4),
        "period_returns": [round(float(r), 8) for r in ls_arr],
    }

    # print("Step 8: Quantile & Decay...", flush=True)
    # ── 4. 分层收益 ──
    q_annual = {}
    quantile_returns = {}
    for q in range(1, n_quantiles + 1):
        arr = np.array(q_ret_accum[f"Q{q}"])
        q_annual[f"Q{q}"] = round(float(arr.mean()) * ann_factor, 6)
        quantile_returns[f"Q{q}"] = [round(float(x), 8) for x in arr]

    q_labels = list(range(1, n_quantiles + 1))
    q_means = [float(np.mean(q_ret_accum[f"Q{q}"])) if len(q_ret_accum[f"Q{q}"]) > 0 else 0 for q in q_labels]
    if len(q_labels) >= 3:
        # 修正：如果 Q1 收益最高，Q5 收益最低，q_means 递减，此时 Spearman 应当为正数
        mono_stat, mono_p = stats.spearmanr([-x for x in q_labels], q_means)
        if pd.isna(mono_stat):
            mono_stat, mono_p = 0, 1
    else:
        mono_stat, mono_p = 0, 1

    quantile_result = {
        "quantile_annual_returns": q_annual,
        "quantile_returns": quantile_returns,
        "monotonicity_score": round(mono_stat, 4),
        "monotonicity_p_value": round(mono_p, 6),
        "monotonicity_significant": bool(mono_p < 0.05),
        "long_short_annual_return_via_quantile": round(
            q_annual.get("Q1", 0) - q_annual.get(f"Q{n_quantiles}", 0), 6
        ),
    }

    # ── 5. 信息衰减 (使用真实后延数据) ──
    ic_decay = {}
    for d in decay_days:
        arr = real_ic_decay[d]
        if len(arr) > 0:
            ic_decay[d] = float(round(np.mean(arr), 6))
        else:
            ic_decay[d] = 0.0

    half_life = forward_days
    # 基准 IC 是 H=1 时的 Rank IC
    base_ic = abs(ic_decay.get(1, 0))
    for d in sorted(ic_decay.keys()):
        if abs(ic_decay[d]) <= base_ic / 2:
            half_life = d
            break
    # 如果所有测算的 decay 天数内都没衰减到一半，记为最大的 decay 天数
    if half_life == forward_days and len(ic_decay) > 0 and abs(ic_decay[max(ic_decay.keys())]) > base_ic / 2:
        half_life = max(ic_decay.keys())

    # ── 6. 最终判断 ──
    ic_rank = ic_result["rank"]
    ic_strength = "强" if abs(ic_rank["mean"]) > 0.05 else "中" if abs(ic_rank["mean"]) > 0.02 else "弱"
    ic_verdict = "✅" if ic_rank["significant_5pct"] else "❌"
    ls_significant = ls_p < 0.05 and ls_sharpe > 0.5
    ls_verdict = "✅" if ls_significant else "❌" if ls_p < 0.05 else "⚠️"
    verdict = "可用" if (ic_rank["significant_5pct"] and ls_significant) else \
              "可观" if ic_rank["significant_5pct"] else "不可用"

    result = {
        "factor": description or expression,
        "expression": auto_adj_expr,
        "original_expression": expression,
        "config": {
            "forward_days": forward_days,
            "start_time": start_time,
            "end_time": end_time,
            "total_days": total_days,
            "n_quantiles": n_quantiles,
            "despike": despike,
            "standardize": standardize,
            "neutralize": neutralize,
        },
        "ic_analysis": ic_result,
        "rebalancing": reb_result,
        "quantile_analysis": quantile_result,
        "ic_decay": ic_decay,
        "half_life": half_life,
        "verdict": {
            "ic_sorting_ability": f"{ic_strength} {ic_verdict}",
            "long_short_profitability": ls_verdict,
            "conclusion": verdict,
        },
    }

    return _convert_numpy(result)


# ─── CLI ─────────────────────────────────────────────────────────

def print_report(result: dict):
    """格式化打印回测报告。"""
    if "error" in result:
        print(f"\n{result.get('expression', '?')}")
        print(f"  ❌ 错误: {result['error']}")
        return

    c = result["config"]
    ic = result["ic_analysis"]
    p = ic["pearson"]
    r = ic["rank"]
    reb = result["rebalancing"]
    qa = result["quantile_analysis"]
    nq = c.get("n_quantiles", 5)

    print(f"\n{result['expression']}")
    print(f"{'=' * 60}")

    # ── IC 分析 ──
    print(f"\n  ── IC 分析 ──")
    print(f"    Rank_IC:      {r['mean']:.4f}   Rank_IC_IR: {r['ir']:.4f}  "
          f"{'✅' if r['significant_5pct'] else '❌'} (p={r['p_value']:.4f})  "
          f"正天数: {r['positive_ratio']:.0%}")
    print(f"    Pearson_IC:   {p['mean']:.4f}   Pearson_IR: {p['ir']:.4f}  "
          f"{'✅' if p['significant_5pct'] else '❌'} (p={p['p_value']:.4f})  "
          f"正天数: {p['positive_ratio']:.0%}")
    print(f"    有效天数: {r['n_days']}天")

    # ── 分层回测 ──
    print(f"\n  ── 分层回测 ({nq}分位) ──")
    print(f"    {'组别':<8}{'年化收益':<16}{'超额p值':<14}")
    for q in sorted(qa["quantile_annual_returns"].keys()):
        # Q1(因子最大)=做多, Q5(因子最小)=做空
        label = "做多" if q == "Q1" else "做空" if q == f"Q{nq}" else ""
        ann_ret = qa["quantile_annual_returns"][q]
        q_returns = np.array(qa.get("quantile_returns", {}).get(q, [0]))
        if len(q_returns) > 1:
            _, qp = stats.ttest_1samp(q_returns, 0)
        else:
            qp = 1
        sig = "✅" if qp < 0.05 else ""
        marker = f"  ← {label}" if label else ""
        print(f"    {q:<6} {ann_ret:+.4f}      p={qp:.4f}  {sig:3s} {marker}")
    ls_val = reb["long_short_annual_return"]
    print(f"    多空年化:    {'+' if ls_val >= 0 else ''}{ls_val:.4f}  Sharpe={reb['long_short_sharpe']:.4f}")
    print(f"    多空p值:  {reb['long_short_p_value']:.4f}  {'✅ 显著' if reb['long_short_significant'] else '不显著'}")
    print(f"    单调性:   {qa['monotonicity_score']:+.4f}  p={qa['monotonicity_p_value']:.4f}")
    print(f"    换手率:   {reb.get('turnover', 0):.4f}")

    # ── 信息衰减 ──
    decay = result.get("ic_decay", {})
    print(f"\n  ── 信息衰减 ──")
    h_strs = [f"H={h}: {decay[h]:+.4f}" for h in sorted(decay.keys()) if h <= 20]
    print("    " + ", ".join(h_strs))
    print(f"    半衰期: >={result.get('half_life', 1):.1f} 天 (以 H=1 的 IC 为基准衰减至一半)")

    # ── 配置 ──
    print(f"\n  ── 配置 ──")
    print(f"    时间: {c['start_time']} → {c['end_time']}")
    print(f"    Horizon: {c['forward_days']}日")
    parts = [
        "去极值=是" if c.get("despike", True) else "去极值=否",
        "标准化=是" if c.get("standardize", True) else "标准化=否",
        "中性化=是" if c.get("neutralize", False) else "中性化=否",
    ]
    print("    " + " ".join(parts))


# ── 主入口 ──
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="因子评价引擎")
    parser.add_argument("--expr", required=True, help="因子表达式")
    parser.add_argument("--desc", default="", help="因子描述")
    parser.add_argument("--start", default="2023-01-01", help="开始日期", type=str)
    parser.add_argument("--end", default="2023-12-31", help="结束日期", type=str)
    parser.add_argument("--forward", type=int, default=1, help="预测周期(天)")
    parser.add_argument("--no-despike", action="store_true", help="不进行去极值")
    parser.add_argument("--no-standardize", action="store_true", help="不进行标准化")
    parser.add_argument("--neutralize", action="store_true", help="市值中性化")
    parser.add_argument("--json", action="store_true", help="输出JSON")
    args = parser.parse_args()

    result = evaluate_factor(
        expression=args.expr, description=args.desc,
        start_time=args.start, end_time=args.end,
        forward_days=args.forward,
        despike=not args.no_despike, standardize=not args.no_standardize,
        neutralize=args.neutralize,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)