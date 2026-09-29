"""Quick LM Studio model lifecycle smoke test.

For each configured model:

    unload all
    load model
    verify model is loaded with `lms ps`
    run exactly one dataset case
    unload all
    verify models are unloaded

This script is intentionally small and is meant to verify that:
1. all three models can be loaded;
2. inference through the existing LogicMUS-Eval pipeline works;
3. models can be unloaded;
4. the next model can be loaded afterwards.

Usage:

    uv run python scripts/test_model_lifecycle.py

Optional:

    uv run python scripts/test_model_lifecycle.py `
        --dataset-dir data/generated_cases `
        --strategy direct
"""

import argparse
import subprocess
import time
from pathlib import Path

from logicmus_eval.evaluate_llm import run_evaluation


# ---------------------------------------------------------------------------
# LM Studio model configuration
# ---------------------------------------------------------------------------

# IMPORTANT:
# `load_key` is the actual LM Studio model key.
# `model_name` is the value passed to your existing LiteLLM pipeline.
#
# They are intentionally kept separately because these two identifiers
# are not always identical.
MODELS: list[dict[str, str]] = [
    {
        "name": "Qwen2.5-Coder-14B",
        "load_key": "qwen2.5-coder-14b-instruct",
        "model_name": "openai/qwen2.5-coder-14b-instruct",
    },
    {
        "name": "Gemma-4-E4B",
        "load_key": "google/gemma-4-e4b",
        "model_name": "openai/google/gemma-4-e4b",
    },
    {
        "name": "GPT-OSS-20B",
        "load_key": "openai/gpt-oss-20b",
        "model_name": "openai/gpt-oss-20b",
    },
]


# Conservative settings for the smoke test.
#
# 4096 is enough for checking the pipeline and avoids unnecessarily
# allocating a huge KV cache.
GPU_OFFLOAD = "max"
CONTEXT_LENGTH = 4096


def run_lms(*args: str) -> subprocess.CompletedProcess[str]:
    """Run an LM Studio CLI command."""
    command = ["lms", *args]

    print(
        f"[LMS] {' '.join(command)}",
        flush=True,
    )

    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
    )


def unload_all() -> None:
    """Unload all currently loaded LM Studio models."""
    result = run_lms("unload", "--all")

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


def show_loaded_models() -> str:
    """Return and print currently loaded models."""
    result = run_lms("ps")

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


def load_model(load_key: str) -> float:
    """Load one model and return loading time."""
    print(
        f"[LOAD] {load_key}",
        flush=True,
    )

    started = time.perf_counter()

    run_lms(
        "load",
        load_key,
        "--gpu",
        GPU_OFFLOAD,
        "--context-length",
        str(CONTEXT_LENGTH),
    )

    elapsed = time.perf_counter() - started

    print(
        f"[LOAD OK] {load_key} "
        f"({elapsed:.2f}s)",
        flush=True,
    )

    return elapsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/generated_cases"),
        help=(
            "Directory containing dataset_v1_frozen.jsonl "
            "(default: data/generated_cases)"
        ),
    )

    parser.add_argument(
        "--strategy",
        choices=["direct", "z3"],
        default="direct",
        help="Evaluation strategy for the one test case.",
    )

    args = parser.parse_args()

    dataset_file = (
        args.dataset_dir
        / "dataset_v1_frozen.jsonl"
    )

    if not dataset_file.exists():
        raise SystemExit(
            f"[ERROR] Dataset not found: {dataset_file}"
        )

    timestamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    output_dir = (
        Path("experiments")
        / f"{timestamp}_model_lifecycle_test"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 72)
    print("LogicMUS-Eval / LM Studio lifecycle smoke test")
    print("=" * 72)

    print(
        f"Dataset : {dataset_file}",
        flush=True,
    )

    print(
        f"Strategy: {args.strategy}",
        flush=True,
    )

    print(
        f"Output  : {output_dir}",
        flush=True,
    )

    print(
        f"Context : {CONTEXT_LENGTH}",
        flush=True,
    )

    # Always start from a clean LM Studio state.
    print("\n[CLEANUP] unloading any existing models", flush=True)

    try:
        unload_all()
    except subprocess.CalledProcessError as exc:
        print(
            f"[WARN] initial unload failed: {exc}",
            flush=True,
        )

    show_loaded_models()

    results: list[dict[str, object]] = []

    try:
        for model in MODELS:
            name = model["name"]
            load_key = model["load_key"]
            model_name = model["model_name"]

            print("\n")
            print("=" * 72)
            print(f"MODEL: {name}")
            print(f"LM Studio key: {load_key}")
            print(f"LiteLLM name:  {model_name}")
            print("=" * 72)

            loaded = False
            load_time = 0.0
            evaluation_ok = False

            try:
                # Make absolutely sure no previous model remains.
                print(
                    "\n[CLEANUP] before loading",
                    flush=True,
                )
                unload_all()

                show_loaded_models()

                # ------------------------------------------------------
                # Load
                # ------------------------------------------------------

                load_time = load_model(load_key)
                loaded = True

                # ------------------------------------------------------
                # Verify loaded model
                # ------------------------------------------------------

                loaded_output = show_loaded_models()

                if not loaded_output:
                    raise RuntimeError(
                        "lms load returned successfully, but "
                        "`lms ps` reported no loaded model."
                    )

                # ------------------------------------------------------
                # One actual LogicMUS-Eval request
                # ------------------------------------------------------

                safe_name = (
                    name
                    .lower()
                    .replace(" ", "_")
                    .replace("-", "_")
                )

                report_name = (
                    f"{safe_name}_{args.strategy}_one_case.json"
                )

                print(
                    "\n[EVAL] running exactly 1 dataset case",
                    flush=True,
                )

                evaluation_started = (
                    time.perf_counter()
                )

                run_evaluation(
                    dataset_dir=str(args.dataset_dir),
                    model_name=model_name,
                    strategy_name=args.strategy,
                    limit=1,
                    output_file=report_name,
                )

                evaluation_time = (
                    time.perf_counter()
                    - evaluation_started
                )

                report_path = (
                    args.dataset_dir
                    / report_name
                )

                if not report_path.exists():
                    raise FileNotFoundError(
                        "Evaluation returned successfully, "
                        f"but report was not found: {report_path}"
                    )

                evaluation_ok = True

                print(
                    f"[EVAL OK] {report_path} "
                    f"({evaluation_time:.2f}s)",
                    flush=True,
                )

                results.append(
                    {
                        "model": name,
                        "load_key": load_key,
                        "model_name": model_name,
                        "load_time_seconds": load_time,
                        "evaluation_time_seconds": evaluation_time,
                        "evaluation_ok": True,
                        "report": str(report_path),
                    }
                )

            except Exception as exc:
                print(
                    f"[FAIL] {name}: {exc}",
                    flush=True,
                )

                results.append(
                    {
                        "model": name,
                        "load_key": load_key,
                        "model_name": model_name,
                        "load_time_seconds": load_time,
                        "evaluation_ok": evaluation_ok,
                        "error": str(exc),
                    }
                )

            finally:
                # ------------------------------------------------------
                # Unload
                # ------------------------------------------------------

                if loaded:
                    print(
                        "\n[UNLOAD] unloading model",
                        flush=True,
                    )

                    try:
                        unload_all()
                    except subprocess.CalledProcessError as exc:
                        print(
                            f"[UNLOAD FAIL] {exc}",
                            flush=True,
                        )

                print(
                    "\n[VERIFY] models after unload",
                    flush=True,
                )

                show_loaded_models()

    finally:
        # Final cleanup in case something unexpected happened.
        print(
            "\n[FINAL CLEANUP] unloading all models",
            flush=True,
        )

        try:
            unload_all()
        except subprocess.CalledProcessError as exc:
            print(
                f"[WARN] final unload failed: {exc}",
                flush=True,
            )

    # --------------------------------------------------------------
    # Summary
    # --------------------------------------------------------------

    print("\n")
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)

    for result in results:
        status = (
            "OK"
            if result["evaluation_ok"]
            else "FAIL"
        )

        print(
            f"{status:4} | "
            f"{result['model']} | "
            f"load={result['load_time_seconds']:.2f}s",
            flush=True,
        )

        if "evaluation_time_seconds" in result:
            print(
                f"       evaluation="
                f"{result['evaluation_time_seconds']:.2f}s",
                flush=True,
            )

        if "error" in result:
            print(
                f"       error={result['error']}",
                flush=True,
            )

    print(
        "\n[DONE] lifecycle test finished",
        flush=True,
    )


if __name__ == "__main__":
    main()