# model_router.py
#
# Central model dispatcher for the note pipeline.
# Usage:
#   from model_router import get_model, log_usage
#   model = get_model("tagging")          # returns e.g. "claude-sonnet-4-5"
#   log_usage("claude-sonnet-4-5", tokens=1200)
#
# Each task has an ordered priority list. The router picks the first model
# that still has quota remaining today. If all models are exhausted, it
# returns the last one in the list anyway (soft fallback — don't hard-crash).

import os
import json
from datetime import date

# ─────────────────────────────────────────────────────────────
# Quota storage
# ─────────────────────────────────────────────────────────────

_DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_QUOTA_PATH = os.path.join(_DATA_DIR, "quota.json")


# ─────────────────────────────────────────────────────────────
# Model catalogue
# Each entry: daily_token_limit (soft cap — router avoids over this)
# ─────────────────────────────────────────────────────────────

MODELS = {
    # ── Google Gemini ──────────────────────────────────────
    "gemini-3.5-flash": {
        "provider":          "gemini",
        "daily_token_limit": 1_000_000,
    },
    "gemini-3.1-flash-lite": {
        "provider":          "gemini",
        "daily_token_limit": 2_000_000,
    },
}


# ─────────────────────────────────────────────────────────────
# Task → priority list
# First model in the list is preferred; falls back in order.
# ─────────────────────────────────────────────────────────────

TASK_ROUTES = {
    # Gemini handles vision-based transcription (image input required)
    "transcription": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],

    "tagging": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
    "matching": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
    "formatting": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
    "exam_gen": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
    "summarization": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
    "chat": [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
}


# ─────────────────────────────────────────────────────────────
# Quota I/O
# ─────────────────────────────────────────────────────────────

def _load_quota() -> dict:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(_QUOTA_PATH):
        return {}
    with open(_QUOTA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_quota(quota: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_QUOTA_PATH, "w", encoding="utf-8") as f:
        json.dump(quota, f, indent=2)


def _today() -> str:
    return str(date.today())


def _tokens_used_today(quota: dict, model: str) -> int:
    today = _today()
    return quota.get(today, {}).get(model, 0)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def get_model(task: str) -> str:
    """
    Returns the best available model for the given task.

    Args:
        task: one of the keys in TASK_ROUTES
              ("transcription", "tagging", "matching",
               "formatting", "exam_gen", "summarization", "chat")

    Returns:
        model name string — always returns something (soft fallback)
    """
    if task not in TASK_ROUTES:
        raise ValueError(
            f"Unknown task '{task}'. Valid tasks: {list(TASK_ROUTES.keys())}"
        )

    priority = TASK_ROUTES[task]
    quota    = _load_quota()

    for model in priority:
        cfg   = MODELS.get(model, {})
        limit = cfg.get("daily_token_limit", 0)
        used  = _tokens_used_today(quota, model)
        if used < limit:
            return model

    # All models exhausted — soft fallback to last in priority list
    fallback = priority[-1]
    print(f"  [model_router] All models exhausted for '{task}', soft-falling back to {fallback}")
    return fallback


def log_usage(model: str, tokens: int) -> None:
    """
    Records token usage for a model against today's quota.

    Args:
        model:  model name string (must be a key in MODELS)
        tokens: number of tokens consumed in this call
    """
    if tokens <= 0:
        return

    quota = _load_quota()
    today = _today()

    if today not in quota:
        # Prune old dates — keep only last 7 days to avoid unbounded growth
        old_dates = sorted(quota.keys())[:-6] if len(quota) >= 7 else []
        for old in old_dates:
            del quota[old]
        quota[today] = {}

    if model not in quota[today]:
        quota[today][model] = 0

    quota[today][model] += tokens
    _save_quota(quota)


def get_usage_report() -> dict:
    """
    Returns today's token usage across all models.
    Useful for the Flask UI stats panel.

    Returns:
        {
          "date": "2026-06-01",
          "usage": {
            "claude-sonnet-4-5": {"used": 12400, "limit": 500000, "pct": 2.5},
            ...
          }
        }
    """
    quota = _load_quota()
    today = _today()
    today_usage = quota.get(today, {})

    report = {"date": today, "usage": {}}

    for model, cfg in MODELS.items():
        used  = today_usage.get(model, 0)
        limit = cfg.get("daily_token_limit", 1)
        report["usage"][model] = {
            "provider": cfg.get("provider", "unknown"),
            "used":     used,
            "limit":    limit,
            "pct":      round(used / limit * 100, 1),
        }

    return report


# ─────────────────────────────────────────────────────────────
# Debug utility
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Model Router — Today's Usage ===\n")
    report = get_usage_report()
    print(f"Date: {report['date']}\n")
    for model, stats in report["usage"].items():
        bar_filled = int(stats["pct"] / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        print(f"  {model}")
        print(f"    [{bar}] {stats['pct']}%  ({stats['used']:,} / {stats['limit']:,} tokens)")
        print()

    print("=== Task Routing Preview ===\n")
    for task in TASK_ROUTES:
        model = get_model(task)
        print(f"  {task:<16} → {model}")