"""Offline audit of predeclared seeds; no model inference or seed selection.

Run: python -m scripts.audit_generation --output data/v2_audit.json
"""

import argparse
import json
from pathlib import Path

from logicmus_eval.leakage import calculate_leakage
from logicmus_eval.run_pipeline import (
    GenerationConfig,
    generate_dataset,
    verify_dataset_correctness,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 42, 2026])
    parser.add_argument("--pairs", type=int, default=25)
    parser.add_argument("--rules", type=int, default=20)
    parser.add_argument("--mus-sizes", type=int, nargs="+", default=[2, 3, 4, 5])
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reports = []
    for seed in args.seeds:
        config = GenerationConfig(
            args.mus_sizes, args.pairs, args.rules, seed, "unused", args.threshold
        )
        dataset = generate_dataset(config)
        validation = verify_dataset_correctness(dataset)
        leakage = calculate_leakage(dataset, args.mus_sizes)
        report = {
            "seed": seed,
            "cases": len(dataset),
            "validation": validation.model_dump(),
            "leakage": leakage.model_dump(),
            "acceptance": leakage.acceptance(args.threshold).model_dump(),
        }
        reports.append(report)
        print(
            json.dumps(
                {
                    "seed": seed,
                    "word_balanced_accuracy": leakage.global_word.mean_balanced_accuracy,
                    "char_balanced_accuracy": leakage.global_char.mean_balanced_accuracy,
                    "passed": report["acceptance"]["passed"],
                }
            ),
            flush=True,
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "seeds_predeclared": args.seeds,
                    "pairs": args.pairs,
                    "total_rules": args.rules,
                    "mus_sizes": args.mus_sizes,
                    "reports": reports,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
