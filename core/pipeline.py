"""Agent pipeline: Proposer, Builder, Critic (A+B debate), Refiner pipeline (direction→coder→verify→criticA)."""

import json, os
from core.llm import llm_call, count_ops
from core.config import STRICTNESS


# ──────────────────────────────────────────────
# Proposer
# ──────────────────────────────────────────────

def propose(task: str, recent_hypotheses: list[str]) -> str:
    """Generate one hypothesis based on the dynamic task definition."""
    sys_p = (
        "You are a creative quant researcher. Propose ONE specific, testable hypothesis "
        "based on the given Task. You MUST ground your hypothesis in behavioral finance principles, "
        "economic theory, statistics, or probability theory. Be precise about the mechanism and mathematical logic. "
        "Output ONLY the hypothesis text (1-2 sentences)."
    )
    user = f"Task: {task}"
    if recent_hypotheses:
        user += f"\n\nAvoid repeating: {json.dumps(recent_hypotheses)}"
    hypothesis = llm_call(sys_p, user, temp=0.8, label="proposer")
    if not hypothesis:
        hypothesis = "5-day momentum scaled by 20-day volatility predicts next-day returns."
    return hypothesis.split("\n")[0][:200]


# ──────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────

def build_expressions(hypothesis: str, count: int = 3) -> list[str]:
    """Generate count Qlib factor expressions from a hypothesis."""
    # 动态加载防坑指南
    try:
        with open("prompts/syntax_pitfalls.md", "r") as f:
            pitfalls = f.read()
    except Exception:
        pitfalls = ""

    sys_b = (
        f"Generate exactly {count} DIFFERENT Qlib factor expressions for the given hypothesis. "
        "You MUST self-check your expressions before outputting.\n"
        f"Available Features: {config.FEATURES}\n"
        "AVOID: Do NOT use features not listed above.\n"
        f"Available Operators: {config.OPERATORS}\n"
        "CRITICAL: Rank(x,N) MUST have a window N > 0 (Time-series percentile). NEVER use N=0. Std(x,N) MUST have window N. "
        "Every operator needs its window parameter.\n"
        "CRITICAL: And(A,B) and Or(A,B) take EXACTLY 2 arguments. "
        "For 3+ conditions use nesting: And(A, And(B, C)).\n"
        "CRITICAL: DO NOT use unary minus (-) on operators like -Corr(). Multiply by -1 instead: (-1 * Corr()).\n"
        f"\n=== STRICT SYNTAX PITFALLS TO AVOID ===\n{pitfalls}\n=====================================\n"
        "You are encouraged to use ANY valid Qlib operators to implement your ideas. Do not limit yourself to basic ones.\n"
        "OUTPUT FORMAT (MUST BE JSON):\n"
        "```json\n"
        "{\n"
        "  \"self_check\": \"Verify: Are there missing window parameters? Are there unary minus operators? Are And/Or 2 arguments?\",\n"
        "  \"expressions\": [\"expr1\", \"expr2\"]\n"
        "}\n"
        "```"
    )
    user = f"Hypothesis: {hypothesis}\n\nGenerate {count} diverse expressions."
    text = llm_call(sys_b, user, temp=0.3, label="builder")
    expressions = []
    if text:
        try:
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].strip()
            data = json.loads(text)
            if isinstance(data, list):
                expressions = data
            elif isinstance(data, dict):
                print(f"   🕵️‍♂️ Builder self-check: {data.get('self_check', '')[:100]}...", flush=True)
                expressions = data.get("expressions", [])
        except json.JSONDecodeError:
            pass
    if not isinstance(expressions, list) or len(expressions) == 0:
        print("   ⚠️ Builder failed, using defaults", flush=True)
        expressions = [
            "Delta($close, 5)",
            "Delta($close, 5) / (Std($close, 20) + 0.001)",
            "Rank(Delta($close, 5), 20)",
        ]
    return expressions


# ──────────────────────────────────────────────
# Critic (A + B debate) — v2
# ──────────────────────────────────────────────

import json
import os
import datetime
import core.config as config
from core.llm import llm_call

def handle_syntax_error(expr: str, err_msg: str, stage: str, iteration: int):
    """
    1. Log the syntax error to pool/syntax_errors.jsonl.
    2. Check for repeats.
    3. Use LLM to automatically update prompts/syntax_pitfalls.md.
    """
    pool_file = "pool/syntax_errors.jsonl"
    os.makedirs(os.path.dirname(pool_file), exist_ok=True)
    
    repeat_count = 0
    try:
        with open(pool_file, "r") as f:
            for line in f:
                data = json.loads(line)
                if data.get("error", "")[:40] == err_msg[:40]:
                    repeat_count += 1
    except Exception:
        pass
    
    # Write to pool
    try:
        with open(pool_file, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.datetime.now().isoformat(),
                "iteration": iteration,
                "stage": stage,
                "expression": expr,
                "error": err_msg
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Update Pitfalls prompt
    pitfalls_path = "prompts/syntax_pitfalls.md"
    os.makedirs(os.path.dirname(pitfalls_path), exist_ok=True)
    try:
        with open(pitfalls_path, "r") as f:
            current_guide = f.read()
    except Exception:
        current_guide = ""

    sys_prompt = "You are a Qlib expert maintaining the 'Qlib Syntax Pitfalls Guide'. You will receive a new syntax error and the current guide. Your task is to output the FULL UPDATED MARKDOWN GUIDE."
    
    if repeat_count > 0:
        instruction = f"This error has occurred {repeat_count + 1} times! Find the relevant section and add a 🚨 CRITICAL REPEATED ERROR warning. CRITICAL: KEEP THE GUIDE EXTREMELY CONCISE. DO NOT append redundant examples of the same error. Keep only ONE clear example and the fix."
    else:
        instruction = "This is a NEW error. Append a new SHORT AND CONCISE section explaining the cause and the exact fix."

    user_prompt = f"""
CURRENT GUIDE:
{current_guide}

NEW ERROR EVENT:
Expression: {expr}
Error Message: {err_msg}

INSTRUCTION:
{instruction}

Output ONLY the full updated Markdown text. Do not wrap in ```markdown blocks if possible.
"""
    print(f"      🤖 [Auto-Prompt] Analyzing syntax error (Repeats: {repeat_count})...", flush=True)
    updated_guide = llm_call(sys_prompt, user_prompt, temp=0.2, label="update_syntax_guide")
    
    if updated_guide:
        if updated_guide.startswith("```markdown"):
            updated_guide = updated_guide[11:-3].strip()
        elif updated_guide.startswith("```"):
            updated_guide = updated_guide[3:-3].strip()
            
        with open(pitfalls_path, "w") as f:
            f.write(updated_guide)
        print(f"      ✅ [Auto-Prompt] syntax_pitfalls.md updated!", flush=True)

def critic_debate(expr: str, metrics: dict, thresholds: dict):
    """
    Critic A (严父): checks each metric comprehensively, reports failures + suggestions.
    Critic B (慈母): finds strengths (IC / return / monotonicity) and structural beauty.

    Returns:
        verdict_a: "pass" | "reject"
        fails_a: list[str]  — e.g. ["IC=0.015<0.025", "Turn=0.71>0.60"]
        suggestions_a: list[str] — e.g. ["add Rank() to boost IC"]
        verdict_b: "pass" | "reject"
        strengths_b: list[str] — e.g. ["IC=0.032不错", "年化多空16%"]
    """
    ic_val = metrics.get("Rank_IC", 0)
    ir_val = metrics.get("Rank_IC_IR", 0)
    ic_p_val = metrics.get("Rank_IC_P_Value", 1.0)
    ic_pos_rate = metrics.get("Rank_IC_Positive_Rate", 0)
    mono_val = metrics.get("Monotonicity_Score", 0)
    turn_val = metrics.get("Top_Quantile_Daily_Turnover", 1.0)
    annual_ls = metrics.get("Annual_Long_Short_Return", 0)
    sharpe_ls = metrics.get("Annual_Long_Short_Sharpe", 0)

    th = thresholds  # min_ic, min_ic_ir, min_mono

    # ── Critic A (严父): 全维度数字硬检 ──────────────
    fails_a = []
    suggestions_a = []

    b_ic = abs(ic_val)
    if b_ic < th["min_ic"]:
        fails_a.append(f"Rank_IC_abs={b_ic:.4f} < {th['min_ic']}")
        suggestions_a.append("尝试加入时序分位数变换 Rank(x, 20)（注意N不能等于0）或改变均线窗口长度来增强因子线性/秩相关性。")
    
    b_ir = abs(ir_val)
    if b_ir < th["min_ic_ir"]:
        fails_a.append(f"Rank_IC_IR_abs={b_ir:.4f} < {th['min_ic_ir']}")
        suggestions_a.append("因子稳定性不足，可能受到极端行情扰动。建议增加波动率缩放Std()，或者外层嵌套Mean()平滑。")
        
    if ic_p_val > 0.05:
        fails_a.append(f"IC_P_Value={ic_p_val:.4f} > 0.05 (统计不显著)")
        suggestions_a.append("预测能力统计学上不显著(像掷硬币)。尝试改变业务逻辑(如量价背离、波动率惩罚)而不仅仅是换窗口。")

    if abs(ic_pos_rate - 0.5) < 0.02: # 胜率非常接近50%
        fails_a.append(f"IC胜率={ic_pos_rate:.2%} 过于接近50%")
        suggestions_a.append("单日预测胜率无优势，建议转变为长周期预测(例如平滑后做大波段)。")

    b_mono = abs(mono_val)
    if b_mono < th["min_mono"]:
        fails_a.append(f"Monotonicity_abs={b_mono:.4f} < {th['min_mono']}")
        suggestions_a.append("分组收益非单调递增/递减。可能是因子两头强中间弱。尝试时序分位数变换 Rank(x, 20)（注意N不能等于0）或去除两端极值逻辑来改善分层。")
        
    if turn_val > 0.60:
        fails_a.append(f"Turnover={turn_val:.4f} > 0.60")
        suggestions_a.append("换手率极高，会被手续费和滑点吃光利润。必须在外层嵌套延迟 Delay() 或窗口平滑 Mean(expr, 5) 来降频。")
        
    if abs(annual_ls) < 0.03:
        fails_a.append(f"多空年化收益={annual_ls:.2%} 过低")
        suggestions_a.append("即使因子能区分股票，但绝对超额收益微弱。可能是因为拥挤度高或特征没有区分度。")

    verdict_a = "reject" if fails_a else "pass"

    # ── Critic B (慈母): 找亮点 ──────────────
    strengths_b = []
    verdict_b = "reject"

    # 慈母的打捞标准
    if b_ic >= 0.025:
        strengths_b.append(f"Rank IC高达 {b_ic:.4f}，具备极强的预测能力基础！")
        verdict_b = "pass"
    elif b_ir >= 0.4:
        strengths_b.append(f"IR={b_ir:.4f} 非常稳健，哪怕绝对收益不高，也是个很优秀的底仓平滑特征。")
        verdict_b = "pass"
    elif abs(annual_ls) >= 0.10:
        strengths_b.append(f"多空年化达到了惊人的 {annual_ls:.2%}，收益极其暴力！")
        verdict_b = "pass"
    elif b_mono >= 0.8:
        strengths_b.append(f"分组单调性得分 {b_mono:.4f}，分层极其完美，因子结构非常健康。")
        verdict_b = "pass"
    elif turn_val < 0.15 and b_ic > 0.015:
        strengths_b.append(f"换手率仅为 {turn_val:.2%}，同时IC有 {b_ic:.4f}，这是非常难得的长线低频好因子！")
        verdict_b = "pass"

    if not strengths_b:
        strengths_b.append("抱歉，我也没有在这个因子中找到任何抢救的价值。")

    return verdict_a, fails_a, suggestions_a, verdict_b, strengths_b


# ──────────────────────────────────────────────
# Refiner Pipeline — v4（方向→Coder→审核→Critic A二审）
# ──────────────────────────────────────────────

_REFINE_GUIDE = None
def _load_refine_guide() -> str:
    global _REFINE_GUIDE
    if _REFINE_GUIDE is None:
        try:
            p = os.path.join(os.path.dirname(__file__), "..", "prompts", "factor_refine_guide.md")
            with open(p) as f:
                _REFINE_GUIDE = f.read()
        except Exception:
            _REFINE_GUIDE = ""
    return _REFINE_GUIDE


# ── 第1步：Refiner 诊断 → 输出优化方向 ──────────
def refine_diagnose(expr: str, metrics: dict, fails: list[str], suggestions: list[str]) -> dict | None:
    """
    Read guide.md, analyze the factor's problems, output a structured improvement plan.
    Returns {"analysis":"...", "direction":"...", "expected_improvement":"..."} or None.
    """
    guide = _load_refine_guide()
    ms = json.dumps({k: round(v, 4) for k, v in (metrics or {}).items() if isinstance(v, (int, float))}, indent=2)
    fails_text = "\n".join(f"  - {f}" for f in fails) if fails else "  无硬检失败"
    sugg_text = "\n".join(f"  - {s}" for s in suggestions) if suggestions else "  无建议"

    system = (
        "You are a quant factor diagnostician. Analyze the factor's problem and output a structured plan.\n\n"
        "Output raw JSON: "
        '{"analysis":"what is wrong","direction":"exactly what to change and how",'
        '"expected_improvement":"which metric should improve and by how much"}'
    )
    user = (
        f"Expression: {expr}\n"
        f"Test metrics:\n{ms}\n"
        f"Critic A failures:\n{fails_text}\n"
        f"Critic A suggestions:\n{sugg_text}\n\n"
        "=== Factor Optimization Reference Handbook ===\n"
        f"{guide}\n"
        "=============================================\n\n"
        "NOTE: The backtesting engine ALREADY performs cross-sectional Median Absolute Deviation (MAD) despiking "
        "and Z-score standardization on the FINAL evaluation output automatically. Do NOT suggest or add "
        "outermost Z-score or standardization operators in your code generation, as it is redundant.\n\n"
        "Diagnose the problem and give a precise optimization direction."
    )
    text = llm_call(system, user, temp=0.2, label="refine_diagnose")
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return None


# ── 第2步：Coder（复用Builder能力）基于方向改造 ──
def refine_coder(expr: str, diagnosis: dict, attempt: int, verify_feedback: str = "") -> dict | None:
    """
    Coder modifies the expression following the Refiner's direction.
    Returns {"name":"...", "expression":"..."} or None.
    """
    try:
        with open("prompts/syntax_pitfalls.md", "r") as f:
            pitfalls = f.read()
    except Exception:
        pitfalls = ""

    direction = diagnosis.get("direction", "change window sizes")
    system = (
        "You are a Qlib factor coder. Modify the base expression following the given direction.\n"
        "You MUST self-check your expressions before outputting.\n"
        f"Available Features: {config.FEATURES}\n"
        f"Available Operators: {config.OPERATORS}\n"
        "CRITICAL: Every operator needs window N. And/Or take EXACTLY 2 parameters.\n"
        "CRITICAL: DO NOT use unary minus (-) on operators like -Corr(). Multiply by -1 instead.\n"
        f"\n=== STRICT SYNTAX PITFALLS TO AVOID ===\n{pitfalls}\n=====================================\n"
        "RULE: Adjust per the direction. You can use ANY valid Qlib operators. There is no limit on operator calls. No hardcoded +0.0001.\n"
        "OUTPUT FORMAT (MUST BE JSON):\n"
        "```json\n"
        "{\n"
        "  \"self_check\": \"Verify: Are there missing window parameters? Are there unary minus operators?\",\n"
        "  \"name\": \"factor_name\",\n"
        "  \"expression\": \"valid_qlib_expr\"\n"
        "}\n"
        "```"
    )
    user = (
        f"Base expression: {expr}\n"
        f"Optimization direction: {direction}\n"
        f"Attempt {attempt+1}/3: Generate ONE modified expression.\n"
        f"CRITICAL: This is attempt {attempt+1}. You MUST generate an expression DIFFERENT from the Base expression and previous attempts. DO NOT simply output the Base expression again."
    )
    if verify_feedback:
        user += f"\nCRITICAL FEEDBACK FROM VERIFIER: {verify_feedback}\nYou MUST fix this issue and write a new valid expression."

    text = llm_call(system, user, temp=0.4, label="refine_coder")
    if text:
        try:
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].strip()
            data = json.loads(text)
            if isinstance(data, dict):
                if "self_check" in data:
                    print(f"      🕵️‍♂️ Coder self-check: {data.get('self_check', '')[:100]}...", flush=True)
                if "expression" in data:
                    return data
        except json.JSONDecodeError:
            pass
    return None
# ── 第3步：Refiner 审查改造结果 ────────────────
def refine_verify(base_expr: str, new_expr: str, direction: str) -> tuple[bool, str]:
    """
    Refiner checks if the coder's output fits the direction.
    Returns (passed: bool, reason: str).
    """
    if new_expr == base_expr:
        return False, "表达式未改动"

    system = (
        "You verify if a modified Qlib factor roughly matches the optimization direction.\n"
        "Output raw JSON: {\"verdict\":\"pass\"|\"reject\",\"reason\":\"explanation\"}\n"
        "CRITICAL RULES FOR REJECTION:\n"
        "1. You MUST ONLY reject if the modified expression COMPLETELY ignores or goes against the suggested optimization direction.\n"
        "If it attempts to follow the direction, you MUST pass it."
    )
    user = (
        f"Base expression: {base_expr}\n"
        f"Modified expression: {new_expr}\n"
        f"Optimization direction: {direction}\n\n"
        "Verdict?"
    )
    text = llm_call(system, user, temp=0.0, label="refine_verify")
    if text:
        try:
            result = json.loads(text)
            return (result.get("verdict") == "pass", result.get("reason", "unknown"))
        except json.JSONDecodeError:
            pass
    return True, "默认通过（解析失败）"


# ── 第4步：Critic A 二审 ───────────────────────
def critic_a_review(expr: str, metrics: dict, thresholds: dict) -> tuple[bool, list[str]]:
    """
    Critic A reviews after refine.
    Returns (passed: bool, failures: list[str]).
    """
    ic_val = abs(metrics.get("Rank_IC", 0))
    ir_val = abs(metrics.get("Rank_IC_IR", 0))
    ic_p_val = metrics.get("Rank_IC_P_Value", 1.0)
    mono_val = abs(metrics.get("Monotonicity_Score", 0))
    turn_val = metrics.get("Top_Quantile_Daily_Turnover", 1.0)
    th = thresholds

    fails = []
    if ic_val < th["min_ic"]:
        fails.append(f"IC={ic_val:.4f}<{th['min_ic']}")
    if ir_val < th["min_ic_ir"]:
        fails.append(f"IR={ir_val:.4f}<{th['min_ic_ir']}")
    if mono_val < th["min_mono"]:
        fails.append(f"Mono={mono_val:.4f}<{th['min_mono']}")
    if ic_p_val > 0.05:
        fails.append(f"P-value={ic_p_val:.4f}>0.05(不显著)")
    if turn_val > 0.60:
        fails.append(f"Turn={turn_val:.4f}>0.60")

    return (len(fails) == 0, fails)

def refine_post_eval(base_expr: str, base_metrics: dict, new_expr: str, new_metrics: dict, direction: str) -> dict:
    """Evaluate if the modification worked and extract experience."""
    system = (
        "You are a quantitative research reviewer. Compare the base factor and the modified factor.\n"
        "Analyze if the modification met the optimization direction and if the metrics (IC, IR, Mono) improved.\n"
        "Output ONLY raw JSON format:\n"
        "```json\n"
        "{\n"
        "  \"met_expectation\": true/false,\n"
        "  \"experience\": \"Summary of what worked or what failed and why. This will guide the next iteration.\"\n"
        "}\n"
        "```"
    )
    b_m = {k: round(v,4) for k,v in base_metrics.items() if isinstance(v, (int,float))}
    n_m = {k: round(v,4) for k,v in new_metrics.items() if isinstance(v, (int,float))}
    user = (
        f"Base Expr: {base_expr}\nBase Metrics: {json.dumps(b_m)}\n"
        f"Direction: {direction}\n"
        f"New Expr: {new_expr}\nNew Metrics: {json.dumps(n_m)}\n"
        "Did it meet expectations? What is the experience learned?"
    )
    text = llm_call(system, user, temp=0.3, label="refine_post_eval")
    if text:
        try:
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].strip()
            return json.loads(text)
        except:
            pass
    return {"met_expectation": False, "experience": "Parse failed."}

