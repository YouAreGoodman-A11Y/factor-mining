"""Factor pool (alpha / rejected) and evo-trace read/write management."""

import json, os, datetime
from core.config import POOL_DIR
import core.config as config


def load_json(path: str) -> list:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path) as f:
            return json.load(f)
    return []


def save_json(path: str, data: list):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class FactorPool:
    """Manages a single pool (alpha or rejected)."""

    def __init__(self, name: str):
        self.path = os.path.join(POOL_DIR, f"{name}.json")
        self.entries = load_json(self.path)

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, i):
        return self.entries[i]

    @property
    def all(self):
        return self.entries

    def append(self, entry: dict):
        self.entries.append(entry)
        save_json(self.path, self.entries)

    def has_expr(self, expr: str, market: str) -> bool:
        """Check if any entry has the same expression AND the same market."""
        return any(
            e.get("expression", "") == expr and e.get("market", "") == market
            for e in self.entries
        )

    def clear(self):
        self.entries = []
        save_json(self.path, self.entries)


class EvoTrace:
    """Manages the iteration trace."""

    def __init__(self):
        self.path = os.path.join(POOL_DIR, "evo_trace.json")
        self.entries = load_json(self.path)

    def __len__(self):
        return len(self.entries)

    @property
    def all(self):
        return self.entries

    def commit(self, iteration: int, hypothesis: str,
               expression_count: int, accepted: int, rejected: int,
               results: list[dict]):
        entry = {
            "iteration": iteration,
            "timestamp": datetime.datetime.now().isoformat(),
            "hypothesis": hypothesis,
            "expressions": expression_count,
            "accepted": accepted,
            "rejected": rejected,
            "results": results,
        }
        self.entries.append(entry)
        save_json(self.path, self.entries)

    def recent_hypotheses(self, n: int = 5) -> list[str]:
        return [e.get("hypothesis", "") for e in self.entries[-n:]]

    def total_accepted(self) -> int:
        return sum(
            1 for e in self.entries
            for r in e.get("results", [])
            if r.get("decision") == "accept"
        )


def make_alpha_entry(hypothesis: str, expression: str, metrics: dict,
                     pool_size: int, iteration: int, expr_idx: int) -> dict:
    return {
        "hypothesis": hypothesis,
        "expression": expression,
        "market": config.MARKET,
        "metrics": metrics,
        "timestamp": datetime.datetime.now().isoformat(),
        "name": f"alpha_{pool_size + 1}_i{iteration}_e{expr_idx + 1}_{config.MARKET}",
    }


def make_reject_entry(hypothesis: str, expression: str, stage: str,
                      metrics: dict | None = None, reason: str = "") -> dict:
    entry = {
        "hypothesis": hypothesis,
        "expression": expression,
        "market": config.MARKET,
        "stage": stage,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    if metrics:
        entry["metrics"] = metrics
    if reason:
        entry["reason"] = reason
    return entry
