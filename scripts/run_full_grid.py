"""Overnight LogicMUS-Eval experiment grid.

Runs a reproducible multi-factor benchmark across three local LM Studio
models and two evaluation strategies.

Experiment design
-----------------

EXP1: influence of the total number of rules
    MUS = 3
    total_rules = 10, 15, 20, 25, 30

EXP2: influence of MUS size
    total_rules = 30
    mus_size = 2, 3, 4, 5, 7, 10, 15

EXP3: influence of MUS size with approximately fixed noise
    noise = 5
    mus_size / total_rules:
        2 / 7
        3 / 8
        5 / 10
        7 / 12
        10 / 15
        15 / 20

For each configuration:
    pairs SAT/UNSAT = 10
    cases = 20

For each case set:
    direct
    z3

Models:
    Qwen2.5-Coder-14B
    Gemma-4-E4B
    GPT-OSS-20B

Models are loaded once per model session, all experiments are executed,
then the model is unloaded.

Usage
-----
    $env:OPENAI_API_BASE = "http://127.0.0.1:1234/v1"
    $env:OPENAI_API_KEY = "lm-studio"

    uv run python scripts/overnight_grid.py \
        --pairs 10 \
        --context-length 4096

The script is resumable: existing reports are skipped.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from logicmus_eval.enums import ManifestFilename
from logicmus_eval.evaluate_llm import run_evaluation
from logicmus_eval.run_pipeline import GenerationConfig, run_generation


# ============================================================================
# Global configuration
# ============================================================================

DATASET_NAME = ManifestFilename.DATASET_JSONL.value

BASE_SEED = 42

DEFAULT_PAIRS = 10
DEFAULT_CONTEXT_LENGTH = 4096
GPU_OFFLOAD = "max"

STRATEGIES = ["direct", "z3"]


# IMPORTANT:
# load_key = identifier used by `lms load`
# model_name = identifier used by LiteLLM/OpenAI-compatible endpoint
MODELS: list[dict[str, str]] = [
    {
        "label": "Qwen2.5-Coder-14B",
        "load_key": "qwen2.5-coder-14b-instruct",
        "model_name": "openai/qwen2.5-coder-14b-instruct",
    },
    {
        "label": "Gemma-4-E4B",
        "load_key": "google/gemma-4-e4b",
        "model_name": "openai/google/gemma-4-e4b",
    },
    {
        "label": "GPT-OSS-20B",
        "load_key": "openai/gpt-oss-20b",
        "model_name": "openai/gpt-oss-20b",
    },
]


# ============================================================================
# Experiment configuration
# ============================================================================


@dataclass(frozen=True)
class GridConfig:
    """One benchmark configuration."""

    exp: str
    name: str
    mus_size: int
    total_rules: int
    pairs: int
    seed: int


def build_grid(pairs: int) -> list[GridConfig]:
    """Build the full overnight experiment grid."""
    configs: list[GridConfig] = []
    index = 0

    def add(
        exp: str,
        name: str,
        mus_size: int,
        total_rules: int,
    ) -> None:
        nonlocal index

        configs.append(
            GridConfig(
                exp=exp,
                name=name,
                mus_size=mus_size,
                total_rules=total_rules,
                pairs=pairs,
                seed=BASE_SEED + index * 1000,
            )
        )

        index += 1

    # ------------------------------------------------------------------
    # EXP 1
    # Fixed MUS size, increasing total number of rules.
    #
    # IMPORTANT:
    # The generator currently has a 32-predicate pool. At total_rules=40
    # the generator requested 42 unique predicates and failed.
    #
    # Therefore the overnight experiment deliberately stops at 30.
    # ------------------------------------------------------------------
    for total_rules in [10, 15, 20, 25, 30]:
        add(
            exp="exp1_total_rules",
            name=f"mus3_total{total_rules}",
            mus_size=3,
            total_rules=total_rules,
        )

    # ------------------------------------------------------------------
    # EXP 2
    # Fixed total number of rules, increasing MUS size.
    # ------------------------------------------------------------------
    for mus_size in [2, 3, 4, 5, 7, 10, 15]:
        add(
            exp="exp2_mus_size",
            name=f"mus{mus_size}_total30",
            mus_size=mus_size,
            total_rules=30,
        )

    # ------------------------------------------------------------------
    # EXP 3
    # Approximately fixed noise = total_rules - mus_size = 5.
    # ------------------------------------------------------------------
    for mus_size in [2, 3, 5, 7, 10, 15]:
        total_rules = mus_size + 5

        add(
            exp="exp3_stress",
            name=f"mus{mus_size}_total{total_rules}",
            mus_size=mus_size,
            total_rules=total_rules,
        )

    return configs


# ============================================================================
# Helpers
# ============================================================================


def now_iso() -> str:
    """Return the current timezone-aware timestamp."""
    return datetime.now().astimezone().isoformat()


def append_manifest(
    path: Path,
    item: dict[str, Any],
) -> None:
    """Append one record to the experiment manifest."""
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = []

    if not isinstance(data, list):
        raise ValueError(f"Manifest must contain a JSON list: {path}")

    data.append(item)

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================================
# LM Studio
# ============================================================================


def run_lms(
    log_path: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Execute one LM Studio CLI command and log its output."""
    command = ["lms", *args]

    started_at = now_iso()

    print(
        f"[LMS] {' '.join(command)}",
        flush=True,
    )

    result = subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
    )

    with log_path.open(
        "a",
        encoding="utf-8",
    ) as log:
        log.write(
            f"\n[{started_at}] "
            f"$ {' '.join(command)}\n"
        )

        if result.stdout:
            log.write(result.stdout)

        if result.stderr:
            log.write(result.stderr)

    return result


def unload_all(log_path: Path) -> None:
    """Unload every currently loaded LM Studio model."""
    try:
        result = run_lms(
            log_path,
            "unload",
            "--all",
        )

        if result.stdout.strip():
            print(
                result.stdout.strip(),
                flush=True,
            )

        if result.stderr.strip():
            print(
                result.stderr.strip(),
                flush=True,
            )

    except subprocess.CalledProcessError as exc:
        print(
            f"[WARN] `lms unload --all` failed: {exc}",
            flush=True,
        )


def show_loaded_models(log_path: Path) -> str:
    """Return and print the current `lms ps` output."""
    result = run_lms(
        log_path,
        "ps",
    )

    output = result.stdout.strip()

    print(
        "[LMS PS]",
        flush=True,
    )

    if output:
        print(
            output,
            flush=True,
        )
    else:
        print(
            "(no models reported)",
            flush=True,
        )

    return output


def load_model(
    model: dict[str, str],
    context_length: int,
    log_path: Path,
) -> float:
    """Load one LM Studio model and verify that it is loaded."""
    load_key = model["load_key"]

    print(
        f"[LOAD] {model['label']} :: {load_key}",
        flush=True,
    )

    started = time.perf_counter()

    run_lms(
        log_path,
        "load",
        load_key,
        "--gpu",
        GPU_OFFLOAD,
        "--context-length",
        str(context_length),
        "--parallel",
        "1",
    )

    elapsed = time.perf_counter() - started

    print(
        f"[LOAD OK] {model['label']} "
        f"({elapsed:.2f}s)",
        flush=True,
    )

    loaded_output = show_loaded_models(log_path)

    if not loaded_output:
        raise RuntimeError(
            "LM Studio returned successfully from `lms load`, "
            "but `lms ps` reported no loaded models."
        )

    return elapsed


# ============================================================================
# Dataset generation
# ============================================================================


def generate_dataset(
    cfg: GridConfig,
    dataset_dir: Path,
) -> Path:
    """Generate and validate one frozen dataset."""
    dataset_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataset_path = (
        dataset_dir / DATASET_NAME
    )

    # Resume support.
    if dataset_path.exists():
        print(
            f"[DATASET SKIP] {cfg.name}: "
            f"{dataset_path}",
            flush=True,
        )

        return dataset_path

    generation_config = GenerationConfig(
        mus_sizes=[cfg.mus_size],
        pairs_per_group=cfg.pairs,
        total_rules=cfg.total_rules,
        base_seed=cfg.seed,
        output_dir=str(dataset_dir),
    )

    print(
        f"[DATASET] {cfg.name}: "
        f"MUS={cfg.mus_size}, "
        f"total={cfg.total_rules}, "
        f"pairs={cfg.pairs}, "
        f"seed={cfg.seed}",
        flush=True,
    )

    started = time.perf_counter()

    run_generation(
        generation_config,
    )

    elapsed = time.perf_counter() - started

    if not dataset_path.exists():
        raise FileNotFoundError(
            "Dataset generation completed, "
            f"but expected file does not exist: {dataset_path}"
        )

    print(
        f"[DATASET OK] {cfg.name} "
        f"({elapsed:.2f}s)",
        flush=True,
    )

    return dataset_path


# ============================================================================
# Main
# ============================================================================


def main() -> None:
    """Run the complete overnight benchmark."""
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--pairs",
        type=int,
        default=DEFAULT_PAIRS,
        help=(
            "Number of SAT/UNSAT pairs per configuration "
            f"(default: {DEFAULT_PAIRS})"
        ),
    )

    parser.add_argument(
        "--context-length",
        type=int,
        default=DEFAULT_CONTEXT_LENGTH,
        help=(
            "Fixed LM Studio context length for all models "
            f"(default: {DEFAULT_CONTEXT_LENGTH})"
        ),
    )

    args = parser.parse_args()

    if args.pairs < 1:
        raise SystemExit(
            "--pairs must be >= 1"
        )

    if args.context_length < 1:
        raise SystemExit(
            "--context-length must be >= 1"
        )

    # ------------------------------------------------------------------
    # Experiment root.
    # ------------------------------------------------------------------

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    root = (
        Path("experiments")
        / f"{timestamp}_overnight_grid"
    )

    datasets_root = root / "datasets"
    logs_root = root / "logs"

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    datasets_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    logs_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path = root / "manifest.json"
    plan_path = root / "plan.json"

    grid = build_grid(
        args.pairs
    )

    # ------------------------------------------------------------------
    # Save immutable experiment plan.
    # ------------------------------------------------------------------

    plan = {
        "created_at": now_iso(),
        "pairs_per_config": args.pairs,
        "cases_per_config": args.pairs * 2,
        "context_length": args.context_length,
        "gpu_offload": GPU_OFFLOAD,
        "strategies": STRATEGIES,
        "models": MODELS,
        "configuration_count": len(grid),
        "expected_requests": (
            len(grid)
            * args.pairs
            * 2
            * len(STRATEGIES)
            * len(MODELS)
        ),
        "grid": [
            asdict(cfg)
            for cfg in grid
        ],
    }

    plan_path.write_text(
        json.dumps(
            plan,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Root-level manifest is our experiment manifest.
    manifest_path.write_text(
        "[]",
        encoding="utf-8",
    )

    # ------------------------------------------------------------------
    # Startup information.
    # ------------------------------------------------------------------

    print("=" * 80)
    print(
        "LogicMUS-Eval / overnight experiment"
    )
    print("=" * 80)

    print(
        f"Root          : {root}",
        flush=True,
    )

    print(
        f"Configurations: {len(grid)}",
        flush=True,
    )

    print(
        f"Pairs/config  : {args.pairs}",
        flush=True,
    )

    print(
        f"Cases/config  : {args.pairs * 2}",
        flush=True,
    )

    print(
        "Strategies    : "
        + ", ".join(STRATEGIES),
        flush=True,
    )

    print(
        f"Models        : {len(MODELS)}",
        flush=True,
    )

    print(
        f"Context       : {args.context_length}",
        flush=True,
    )

    expected_requests = (
        len(grid)
        * args.pairs
        * 2
        * len(STRATEGIES)
        * len(MODELS)
    )

    print(
        f"Total requests: {expected_requests}",
        flush=True,
    )

    print("=" * 80)

    # ------------------------------------------------------------------
    # STEP 1
    # Generate every dataset before loading any LLM.
    # ------------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "STEP 1: DATASET GENERATION"
    )
    print("=" * 80)

    dataset_paths: dict[str, Path] = {}

    generation_started = time.perf_counter()

    for cfg in grid:
        dataset_dir = (
                datasets_root
                / cfg.exp
                / cfg.name
        )

        try:
            dataset_path = generate_dataset(
                cfg,
                dataset_dir,
            )
        except Exception as e:
            print(
                f"[SKIP] dataset generation failed for {cfg.name}: {e}",
                flush=True,
            )

            append_manifest(
                manifest_path,
                {
                    "type": "dataset",
                    "status": "error",
                    "created_at": now_iso(),
                    "config": asdict(cfg),
                    "error": str(e),
                },
            )

            continue

        dataset_paths[cfg.name] = dataset_path

        append_manifest(
            manifest_path,
            {
                "type": "dataset",
                "status": "ok",
                "created_at": now_iso(),
                "config": asdict(cfg),
                "dataset": str(dataset_path),
            },
        )

    generation_elapsed = (
        time.perf_counter()
        - generation_started
    )

    print(
        "\n[DATASET GENERATION COMPLETE] "
        f"{generation_elapsed:.2f}s",
        flush=True,
    )

    # ------------------------------------------------------------------
    # STEP 2
    # Evaluate all configs model-by-model.
    # ------------------------------------------------------------------

    try:
        for model in MODELS:
            model_label = model["label"]

            safe_model_name = (
                model_label
                .lower()
                .replace(" ", "_")
                .replace("-", "_")
            )

            model_log = (
                logs_root
                / f"{safe_model_name}.log"
            )

            print()
            print("=" * 80)
            print(
                f"MODEL: {model_label}"
            )
            print("=" * 80)

            # Always start from a clean LM Studio state.
            print(
                "\n[CLEANUP] before model load",
                flush=True,
            )

            unload_all(
                model_log
            )

            # We deliberately consider the model load "attempted" before
            # calling lms load so that even a partially successful load is
            # followed by cleanup.
            load_attempted = False
            load_time = 0.0

            session_started_at = now_iso()

            try:
                load_attempted = True

                load_time = load_model(
                    model=model,
                    context_length=args.context_length,
                    log_path=model_log,
                )

                # ------------------------------------------------------
                # All benchmark jobs for this model use ONE loaded model.
                # ------------------------------------------------------

                for cfg in grid:
                    dataset_dir = (
                        datasets_root
                        / cfg.exp
                        / cfg.name
                    )

                    for strategy in STRATEGIES:
                        report_name = (
                            f"{safe_model_name}_"
                            f"{strategy}.json"
                        )

                        report_path = (
                            dataset_dir
                            / report_name
                        )

                        # --------------------------------------------------
                        # Resume support.
                        # --------------------------------------------------

                        if report_path.exists():
                            print(
                                f"[SKIP] "
                                f"{cfg.name} / "
                                f"{model_label} / "
                                f"{strategy}",
                                flush=True,
                            )
                            continue

                        print()
                        print("-" * 80)

                        print(
                            f"[RUN] "
                            f"{cfg.name} | "
                            f"{model_label} | "
                            f"{strategy}",
                            flush=True,
                        )

                        print("-" * 80)

                        started_at = now_iso()
                        started = time.perf_counter()

                        try:
                            run_evaluation(
                                dataset_dir=str(
                                    dataset_dir
                                ),
                                model_name=model[
                                    "model_name"
                                ],
                                strategy_name=strategy,
                                limit=cfg.pairs * 2,
                                output_file=report_name,
                            )

                            elapsed = (
                                time.perf_counter()
                                - started
                            )

                            if not report_path.exists():
                                raise FileNotFoundError(
                                    "Evaluation returned "
                                    "successfully, but the "
                                    f"expected report was not "
                                    f"created: {report_path}"
                                )

                            print(
                                f"[OK] "
                                f"{cfg.name} | "
                                f"{model_label} | "
                                f"{strategy} | "
                                f"{elapsed:.2f}s",
                                flush=True,
                            )

                            append_manifest(
                                manifest_path,
                                {
                                    "type": "report",
                                    "status": "ok",
                                    "started_at": started_at,
                                    "finished_at": now_iso(),
                                    "elapsed_seconds": elapsed,
                                    "session_started_at": (
                                        session_started_at
                                    ),
                                    "load_time_seconds": (
                                        load_time
                                    ),
                                    "config": asdict(
                                        cfg
                                    ),
                                    "model": model[
                                        "model_name"
                                    ],
                                    "model_label": (
                                        model_label
                                    ),
                                    "load_key": model[
                                        "load_key"
                                    ],
                                    "strategy": strategy,
                                    "dataset": str(
                                        dataset_paths[
                                            cfg.name
                                        ]
                                    ),
                                    "report": str(
                                        report_path
                                    ),
                                },
                            )

                        except KeyboardInterrupt:
                            print(
                                "\n[INTERRUPT] "
                                f"{cfg.name} / "
                                f"{model_label} / "
                                f"{strategy}",
                                flush=True,
                            )
                            raise

                        except Exception as exc:
                            elapsed = (
                                time.perf_counter()
                                - started
                            )

                            print(
                                f"[FAIL] "
                                f"{cfg.name} | "
                                f"{model_label} | "
                                f"{strategy}: "
                                f"{exc}",
                                flush=True,
                            )

                            append_manifest(
                                manifest_path,
                                {
                                    "type": "report",
                                    "status": "error",
                                    "started_at": started_at,
                                    "finished_at": now_iso(),
                                    "elapsed_seconds": elapsed,
                                    "session_started_at": (
                                        session_started_at
                                    ),
                                    "load_time_seconds": (
                                        load_time
                                    ),
                                    "config": asdict(
                                        cfg
                                    ),
                                    "model": model[
                                        "model_name"
                                    ],
                                    "model_label": (
                                        model_label
                                    ),
                                    "load_key": model[
                                        "load_key"
                                    ],
                                    "strategy": strategy,
                                    "dataset": str(
                                        dataset_paths[
                                            cfg.name
                                        ]
                                    ),
                                    "report": str(
                                        report_path
                                    ),
                                    "error": str(exc),
                                },
                            )

            finally:
                # ------------------------------------------------------
                # ALWAYS unload the model after this session.
                # ------------------------------------------------------

                if load_attempted:
                    print()
                    print(
                        f"[UNLOAD] {model_label}",
                        flush=True,
                    )

                    unload_all(
                        model_log
                    )

                    print(
                        f"[VERIFY UNLOAD] "
                        f"{model_label}",
                        flush=True,
                    )

                    try:
                        show_loaded_models(
                            model_log
                        )
                    except subprocess.CalledProcessError as exc:
                        print(
                            "[WARN] Could not verify "
                            f"model unload: {exc}",
                            flush=True,
                        )

    finally:
        # ------------------------------------------------------------------
        # Final emergency cleanup.
        # ------------------------------------------------------------------
        print()
        print(
            "[FINAL CLEANUP] unloading all LM Studio models",
            flush=True,
        )

        cleanup_log = (
            logs_root
            / "final_cleanup.log"
        )

        unload_all(
            cleanup_log
        )

    # ----------------------------------------------------------------------
    # Final information.
    # ----------------------------------------------------------------------

    print()
    print("=" * 80)
    print(
        "OVERNIGHT RUN FINISHED"
    )
    print("=" * 80)

    print(
        f"Experiment root: {root}",
        flush=True,
    )

    print(
        f"Plan           : {plan_path}",
        flush=True,
    )

    print(
        f"Manifest       : {manifest_path}",
        flush=True,
    )

    print()
    print(
        "Analyze with:"
    )

    print(
        f"uv run python scripts/analyze.py "
        f"{root}",
        flush=True,
    )


if __name__ == "__main__":
    main()