"""
测试脚本 — 手动跑 factor_evaluator.py 的快速入口
用法: python3 test_evaluator.py
"""

import sys
sys.path.insert(0, ".")

import subprocess

test_cases = [
    # (表达式, 描述, 参数串)
    # ("Ref($close,-1)/$close-1", "短期: 未来1日收益(完美神预言)", '--forward 1 --start 2023-01-01 --end 2023-12-31')
    ("Delta($close, 5) / Std($close, 20)",       "中期: 5日动量/20日波动", '--forward 1 --start 2023-01-01 --end 2023-12-31')
    # ("Rank(Delta($close, 5), 20)",                "排序: 5日动量排名",       '--forward 1 --start 2023-01-01 --end 2023-06-30'),
    # ("Mean($volume, 5)",                          "量类: 5日均量",           '--forward 1 --start 2023-01-01 --end 2023-06-30'),
    # ("Delta($close, 5) / Std($close, 20)",        "H=5: 5日动量/20日波动",   '--forward 5 --start 2023-01-01 --end 2023-06-30'),
    # ("Delta($close, 5) / Std($close, 20)",        "H=20: 5日动量/20日波动",  '--forward 20 --start 2023-01-01 --end 2023-06-30'),
]

for i, (expr, desc, args) in enumerate(test_cases, 1):
    print(f"\n{'#' * 60}")
    print(f"# 测试 {i}/{len(test_cases)}: {desc}")
    print(f"# 表达式: {expr}")
    print(f"# 参数:   {args}")
    print(f"{'#' * 60}")

    cmd = f"/root/.openclaw/workspace-data_engineer/factor_miner_v2/factor_evaluator.py --expr '{expr}' {args}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)

    if result.returncode == 0:
        print(result.stdout)
    else:
        print(f"报错:\n{result.stderr or result.stdout}")
