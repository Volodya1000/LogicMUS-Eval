"""Quick mini-grid runner for LogicMUS-Eval.

Runs a small grid of (mus_size, total_rules) configurations on one
local model and two evaluation strategies. Saves reports and a
manifest.json into experiments/<timestamp>_quick_grid/.

Usage:
    .\\.venv\\Scripts\\Activate.ps1
    python scripts/quick_grid.py
"""

import hashlib
import json
import os
import signal
import time
from pathlib import Path
from typing import TypedDict

from logicmus_eval.evaluate_llm import run_evaluation
from logicmus_eval.logging_utils import configure_logging
from logicmus_eval.run_pipeline import GenerationConfig, run_generation


class GridConfig(TypedDict):
    exp: str
    name: str
    mus_size: int
    total_rules: int


def _hard_exit(signum: int, _frame: object) -> None:
    print(f"\n[INTERRUPT] signal {signum}, forced exit", flush=True)
    os._exit(130)


signal.signal(signal.SIGINT, _hard_exit)
signal.signal(signal.SIGTERM, _hard_exit)


# MODELS: list[str] = [
#     "openai/qwen2.5-coder-14b-instruct",
# ]
MODELS: list[str] = [
    "openai/google/gemma-4-e4b",
]

STRATEGIES: list[str] = ["direct", "z3"]

PAIRS = 10
BASE_SEED = 42

GRID: list[GridConfig] = [
    # --- Experiment 1: fixed mus_size, sweep total_rules (noise sweep) ---
    {
        "exp": "exp1_total_rules",
        "name": "mus3_total10",
        "mus_size": 3,
        "total_rules": 10,
    },
    {
        "exp": "exp1_total_rules",
        "name": "mus3_total20",
        "mus_size": 3,
        "total_rules": 20,
    },
    {
        "exp": "exp1_total_rules",
        "name": "mus3_total30",
        "mus_size": 3,
        "total_rules": 30,
    },
    # --- Experiment 2: fixed total_rules, sweep mus_size (core-size sweep) ---
    {"exp": "exp2_mus_size", "name": "mus2_total20", "mus_size": 2, "total_rules": 20},
    {"exp": "exp2_mus_size", "name": "mus5_total20", "mus_size": 5, "total_rules": 20},
    {
        "exp": "exp2_mus_size",
        "name": "mus10_total20",
        "mus_size": 10,
        "total_rules": 20,
    },
    # --- Experiment 3: stress — large MUS, minimal noise ---
    {"exp": "exp3_stress", "name": "mus15_total18", "mus_size": 15, "total_rules": 18},
]


def _dataset_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    configure_logging()

    out_root = Path("experiments") / f"{time.strftime('%Y%m%d_%H%M%S')}_quick_grid"
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"[QUICK_GRID] output root: {out_root}", flush=True)

    manifest: list[dict[str, object]] = []

    for cfg in GRID:
        cfg_dir = out_root / cfg["name"]
        ds_dir = cfg_dir / "dataset"
        ds_dir.mkdir(parents=True, exist_ok=True)
        dataset_file = ds_dir / "dataset_v1_frozen.jsonl"

        print(
            f"[GEN] {cfg['name']} (mus={cfg['mus_size']}, rules={cfg['total_rules']})",
            flush=True,
        )

        if not dataset_file.exists():
            gen_cfg = GenerationConfig(
                mus_sizes=[cfg["mus_size"]],
                pairs_per_group=PAIRS,
                total_rules=cfg["total_rules"],
                base_seed=BASE_SEED,
                output_dir=str(ds_dir),
            )
            run_generation(gen_cfg)

        sha = _dataset_sha256(dataset_file)
        manifest.append(
            {
                "type": "dataset",
                "config": cfg,
                "dataset_dir": str(ds_dir),
                "dataset_sha256": sha,
            }
        )

        for model in MODELS:
            for strategy in STRATEGIES:
                safe_model = model.replace("/", "_").replace(":", "_")
                report_name = f"{safe_model}_{strategy}.json"
                report_path = ds_dir / report_name

                if report_path.exists():
                    print(f"[SKIP] {report_path}", flush=True)
                else:
                    print(f"[EVAL] {cfg['name']} | {model} | {strategy}", flush=True)
                    run_evaluation(
                        dataset_dir=str(ds_dir),
                        model_name=model,
                        strategy_name=strategy,
                        limit=PAIRS * 2,
                        output_file=report_name,
                    )

                manifest.append(
                    {
                        "type": "report",
                        "config": cfg,
                        "model": model,
                        "strategy": strategy,
                        "report": str(report_path),
                    }
                )

                (out_root / "manifest.json").write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    print(f"[DONE] {out_root}", flush=True)


if __name__ == "__main__":
    main()
