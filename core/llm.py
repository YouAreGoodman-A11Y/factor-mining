"""LLM client wrapper + Qlib expression fixer."""

import json, re, os
import litellm

# Use Gemini by default
MODEL = "gemini/gemini-2.5-pro"

def llm_call(system: str, user: str, temp: float = 0.7, label: str = "") -> str | None:
    """Call LLM via litellm and return parsed text (stripped of markdown fences)."""
    try:
        from core.config import MODEL_PROPOSER, MODEL_CODER, MODEL
        # Heterogeneous engine routing based on label
        if label == "proposer":
            model_name = MODEL_PROPOSER
        elif label in ["builder", "update_syntax_guide", "refine_diagnose", "refine_coder", "refine_verify", "refine_post_eval"]:
            model_name = MODEL_CODER
        else:
            model_name = MODEL_CODER
    except ImportError:
        model_name = MODEL

    if "deepseek" in model_name:
        api_base = "https://api.deepseek.com/v1"
        api_key = os.environ.get("OPENAI_API_KEY")
    elif "gemini" in model_name:
        api_base = None
        api_key = os.environ.get("GEMINI_API_KEY")
    else:
        api_base = None
        api_key = os.environ.get("OPENAI_API_KEY")

    try:
        resp = litellm.completion(
            model=model_name,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temp, 
            timeout=120,
            api_key=api_key,
            api_base=api_base,
            max_retries=2,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return text
    except Exception as e:
        print(f"   ⚠️ [{label}] LLM error: {e}", flush=True)
        return None


def fix_qlib_expr(expr: str) -> str:
    """Auto-fix common Qlib expression issues."""
    fixed = expr
    # Removed dangerous regex-based parenthesis injection that was breaking Sign() and other nested ops.
    # We rely on the LLM prompt to correctly provide window parameters now.
    
    # bare field names → $ prefix
    for field in ['close', 'open', 'high', 'low', 'volume', 'amount']:
        fixed = re.sub(rf'(?<!\$)\b{field}\b', f'${field}', fixed)
    return fixed


def count_ops(expr: str) -> int:
    """Count operator calls — proxy for expression complexity."""
    ops = re.findall(r'(?:Delta|Mean|Std|Sum|Max|Min|Rank|Ref|Corr|Cov|Abs|Sign|Power|Log|If|Ref)\(', expr)
    return len(ops)
