#!/usr/bin/env python3
"""
factor_miner_x — 10‑iteration factor mining pipeline.

Orchestrates: Proposer → Builder → Tester → Critic(A+B) → (Refine loop) → Pool write
All agent logic lives in core/ modules.
"""

import argparse, datetime, gc, sys
import core.config as config
from core.config import TASK, TEST_TIMEOUT, STRICTNESS, LOG_DIR
from core.tester import run_test
from core.pipeline import (
    propose, build_expressions, critic_debate,
    refine_diagnose, refine_coder, refine_verify, critic_a_review, handle_syntax_error
)
from core.pool import FactorPool, EvoTrace, make_alpha_entry, make_reject_entry
from core.llm import count_ops


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--strictness", choices=["relaxed", "normal", "strict"], default="normal")
    parser.add_argument("--market", type=str, default=config.MARKET, help="Qlib market pool (e.g. csi300, all_a_shares)")
    parser.add_argument("--features", type=str, default=config.FEATURES, help="Available base features")
    parser.add_argument("--operators", type=str, default=config.OPERATORS, help="Available operators")
    parser.add_argument("--model", type=str, default=config.MODEL, help="LLM model (e.g. gemini/gemini-3.1-pro-preview)")
    args = parser.parse_args()

    # Apply overrides to global config
    config.MODEL = args.model
    config.MARKET = args.market
    if hasattr(config, "TASK_TEMPLATE"):
        config.TASK = config.TASK_TEMPLATE.format(market=args.market)
    config.FEATURES = args.features
    config.OPERATORS = args.operators

    thresholds = STRICTNESS[args.strictness]

    # Logging
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{LOG_DIR}/run_{config.MARKET}_{timestamp}.log"
    sys.stdout = open(log_file, "a", buffering=1)  # line-buffered = 实时
    sys.stderr = sys.stdout

    # Pools
    alpha_pool = FactorPool("alpha_pool")
    rejected_pool = FactorPool("rejected_pool")
    evo_trace = EvoTrace()

    print(f"\n{'='*60}")
    print(f"  FACTOR MINER X — Stable Run")
    print(f"  Task: {TASK[:60]}...")
    print(f"  Model: deepseek-chat | Strictness: {args.strictness}")
    print(f"  Iterations: {args.iterations} | Timeout: {TEST_TIMEOUT}s")
    print(f"  Market: {config.MARKET}")
    print(f"  Features: {config.FEATURES[:60]}...")
    print(f"  Started: {datetime.datetime.now().isoformat()}")
    print(f"{'='*60}\n", flush=True)

    # Warm-up
    print("⚡ Warming qlib...", flush=True)
    warmup = run_test("Delta($close, 1)", "__warmup__")
    if warmup is not None:
        print("✅ Qlib ready.", flush=True)
    else:
        print("⚠️  Qlib warmup failed (may still work).", flush=True)

    for iteration in range(1, args.iterations + 1):
        print(f"\n{'█'*60}")
        print(f"  ITERATION {iteration}/{args.iterations}")
        print(f"{'█'*60}", flush=True)

        # ── Proposer ──────────────────────────────────────
        print("\n🧠 [Proposer] Generating hypothesis...", flush=True)
        hypothesis = propose(config.TASK, evo_trace.recent_hypotheses(5))
        print(f"   H: {hypothesis}", flush=True)

        # ── Builder ───────────────────────────────────────
        print("\n🔧 [Builder] Generating 3 expressions...", flush=True)
        expressions = build_expressions(hypothesis, 3)
        for i, e in enumerate(expressions):
            print(f"   {i+1}. {e[:80]}…", flush=True)

        # ── Dedup against existing pool ──────────────
        unique_exprs = []
        for e in expressions:
            if alpha_pool.has_expr(e, config.MARKET) or rejected_pool.has_expr(e, config.MARKET):
                print(f"   ⏭️  Skip duplicate: {e[:60]}…", flush=True)
            else:
                unique_exprs.append(e)
        expressions = unique_exprs
        if not expressions:
            print("   ⏭️  All expressions are duplicates. Skipping iteration.", flush=True)
            evo_trace.commit(iteration, hypothesis, 0, 0, 0, [])
            continue

        iteration_results = []
        accepted_here = 0
        rejected_here = 0

        for j, expr in enumerate(expressions):
            print(f"\n{'─'*50}")
            print(f"  📐 {j+1}/{len(expressions)}: {expr[:60]}", flush=True)

            # ── Test base ──────────────────────────────
            metrics = run_test(expr, f"I{iteration}_E{j+1}")
            if "syntax_error" in metrics:
                err_msg = metrics["syntax_error"]
                print(f"      → 🚧 Syntax/Runtime Error: {err_msg}", flush=True)
                handle_syntax_error(expr, err_msg, stage="base_test", iteration=iteration)
                iteration_results.append({"expr": expr, "decision": "syntax_error", "stage": "test_error"})
                continue

            b_ic = abs(metrics.get("Rank_IC", 0))
            b_ir = abs(metrics.get("Rank_IC_IR", 0))
            b_mono = abs(metrics.get("Monotonicity_Score", 0))
            b_turn = metrics.get("Top_Quantile_Daily_Turnover", 1.0)

            # ── Critic A+B debate ─────────────────────
            print("   ⚖️  Critic A (严父) + B (慈母) debating...", flush=True)
            va, fails_a, suggestions_a, vb, strengths_b = critic_debate(expr, metrics, thresholds)

            print(f"      A: {va} | 硬检不过: {fails_a if fails_a else '无'}", flush=True)
            print(f"      B: {vb} | 亮点: {strengths_b}", flush=True)

            # 判罚逻辑：
            #   A pass + B pass → 直接入池
            #   A reject + B pass → 走 Refine (用 A 的 suggestion)
            #   A reject + B reject → 淘汰

            if va == "pass" and vb == "pass":
                print("      → ✅ A+B双通过，直接入池！", flush=True)
                entry = make_alpha_entry(hypothesis, expr, metrics, len(alpha_pool), iteration, j)
                alpha_pool.append(entry)
                accepted_here += 1
                print(f"   🏆 Written to alpha_pool! ({len(alpha_pool)} total)", flush=True)
                iteration_results.append({
                    "expr": expr, "final_expr": expr, "decision": "accept",
                    "rank_ic": b_ic, "ic_ir": b_ir, "stage": "critic_direct",
                })
                gc.collect()
                continue

            if va == "reject" and vb == "reject":
                print("      → ❌ A+B双拒，淘汰", flush=True)
                diag_a = "; ".join(fails_a + suggestions_a) if fails_a else "无"
                rejected_pool.append(make_reject_entry(
                    hypothesis, expr, "critic_reject", metrics, f"A拒B拒: {diag_a}"))
                rejected_here += 1
                iteration_results.append({"expr": expr, "decision": "reject", "stage": "critic_reject"})
                gc.collect()
                continue

            # ── A reject + B pass → Refine Pipeline ──
            print(f"      → 🔧 A拒B过，启动 Refine Pipeline (最多循环3次)", flush=True)
            from core.pipeline import refine_post_eval
            
            final_expr = expr
            final_metrics = metrics
            final_decision = "reject"
            final_reason = ""
            
            base_expr = expr
            base_metrics = metrics
            experience_history = []
            outer_loops = 3
            refined_and_tested = []
            
            for loop_idx in range(outer_loops):
                print(f"   🔄 [Refine Outer Loop] {loop_idx+1}/{outer_loops}...", flush=True)
                
                # 1. 诊断 (包含历史沉淀经验)
                diagnosis = refine_diagnose(base_expr, base_metrics, fails_a, suggestions_a)
                if diagnosis is None:
                    print("      ⚠️  Diagnosis failed, skipping this loop", flush=True)
                    continue
                    
                if experience_history:
                    # 把前几轮的经验塞进方向里
                    diagnosis["direction"] += f"\n\n[PAST EXPERIENCE (USE THIS TO IMPROVE)]: {experience_history[-1]}"
                    
                direction = diagnosis.get("direction", "")
                print(f"      📋 Analysis: {diagnosis.get('analysis','')[:80]}", flush=True)
                print(f"      🎯 Direction: {direction[:120]}", flush=True)
                
                # 2. Coder 修改 -> Refiner 验证 (内循环，最多3次改写)
                inner_attempts = 0
                max_inner = 3
                verify_feedback = ""
                new_expr = ""
                
                while inner_attempts < max_inner:
                    inner_attempts += 1
                    print(f"      🔧 [Coder] Attempt {inner_attempts}/{max_inner}...", flush=True)
                    
                    coded = refine_coder(base_expr, diagnosis, inner_attempts - 1, verify_feedback)
                    if coded is None:
                        print("         ⚠️  Coder failed to generate JSON", flush=True)
                        continue
                    
                    temp_expr = coded.get("expression", "")
                    is_duplicate = (temp_expr == base_expr) or any(temp_expr == ne for ne, _ in refined_and_tested)
                    if not temp_expr or is_duplicate:
                        print("         ⚠️  Same expression or already tested, verifier will reject", flush=True)
                        verify_feedback = "You outputted the same expression again or an already tested one. Provide a NEW expression."
                        continue
                        
                    # 验证
                    print(f"         🔍 Verify: {temp_expr[:70]}...", flush=True)
                    verified, v_reason = refine_verify(base_expr, temp_expr, direction)
                    if not verified:
                        print(f"         ❌ Verify rejected: {v_reason}", flush=True)
                        verify_feedback = v_reason
                        continue
                        
                    print(f"         ✅ Verify passed!", flush=True)
                    new_expr = temp_expr
                    break # 成功通过内循环验证
                    
                if not new_expr:
                    print("      ⚠️ Coder failed to pass verification after 3 attempts.", flush=True)
                    continue
                    
                # 3. 回测新因子
                ref_metrics = run_test(new_expr, f"I{iteration}_E{j+1}_L{loop_idx+1}")
                if "syntax_error" in ref_metrics:
                    err_msg = ref_metrics["syntax_error"]
                    print(f"      ⚠️  Refine Test failed: {err_msg}", flush=True)
                    handle_syntax_error(new_expr, err_msg, stage="refine", iteration=iteration)
                    continue
                    
                refined_and_tested.append((new_expr, ref_metrics))
                
                # 4. Refiner 总结比对经验 (Post Eval)
                reflection = refine_post_eval(base_expr, base_metrics, new_expr, ref_metrics, direction)
                exp_text = reflection.get("experience", "No clear experience.")
                print(f"      🧠 [Reflection] {exp_text[:100]}...", flush=True)
                experience_history.append(exp_text)
                
                # 5. Critic A 判定
                a_passed, a_fails = critic_a_review(new_expr, ref_metrics, thresholds)
                if a_passed:
                    final_decision = "accept"
                    final_expr = new_expr
                    final_metrics = ref_metrics
                    final_reason = "All thresholds passed after refine"
                    print(f"      🎉 REFINED & ACCEPTED! IC={abs(ref_metrics.get('Rank_IC',0)):.4f} IR={abs(ref_metrics.get('Rank_IC_IR',0)):.4f}", flush=True)
                    break
                else:
                    print(f"      💀 Critic A rejects: {' | '.join(a_fails)}", flush=True)
                    # 没过的话，把这次当做新的 base，带着经验进入下一轮大循环
                    base_expr = new_expr
                    base_metrics = ref_metrics
                    fails_a = a_fails
                    
                    final_expr = new_expr
                    final_metrics = ref_metrics
                    final_reason = " | ".join(a_fails)

            # 在退出所有循环后，如果没有被 accept，但也生成过结果，我们在最终选择里挑最好的一个放入淘汰池
            if final_decision == "reject" and refined_and_tested:
                best_score = -1
                best_pair = None
                for ne, nm in refined_and_tested:
                    score = abs(nm.get("Rank_IC", 0)) + abs(nm.get("Rank_IC_IR", 0)) * 3
                    if score > best_score:
                        best_score = score
                        best_pair = (ne, nm)
                if best_pair:
                    final_expr, final_metrics = best_pair
                    final_reason = f"Refine Failed (Best attempt IC={abs(final_metrics.get('Rank_IC',0)):.4f})"

            # ── Record refine result ────────────────
            if final_decision == "accept":
                entry = make_alpha_entry(hypothesis, final_expr, final_metrics,
                                         len(alpha_pool), iteration, j)
                alpha_pool.append(entry)
                accepted_here += 1
                print(f"   🏆 Written to alpha_pool! ({len(alpha_pool)} total)", flush=True)
            else:
                rejected_pool.append(make_reject_entry(
                    hypothesis, final_expr, "refine_failed", final_metrics, final_reason))
                rejected_here += 1

            iteration_results.append({
                "expr": expr, "final_expr": final_expr,
                "decision": final_decision,
                "rank_ic": final_metrics.get("Rank_IC"),
                "ic_ir": final_metrics.get("Rank_IC_IR"),
            })
            gc.collect()

        # ── Evo trace ────────────────────────────────
        evo_trace.commit(iteration, hypothesis,
                         len(expressions), accepted_here, rejected_here,
                         iteration_results)
        print(f"\n  ✅ Iter {iteration}: {accepted_here}A / {rejected_here}R")
        print(f"  Alpha pool: {len(alpha_pool)} | Rejected: {len(rejected_pool)}", flush=True)
        gc.collect()

    total = evo_trace.total_accepted()
    print(f"\n{'='*60}")
    print(f"  RUN COMPLETE — {args.iterations} iterations")
    print(f"  Alpha pool: {len(alpha_pool)} factors")
    print(f"  Rejected pool: {len(rejected_pool)} factors")
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    main()
