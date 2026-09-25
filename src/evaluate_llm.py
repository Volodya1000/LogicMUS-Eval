import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.enums import ManifestFilename
from src.extractor import ExtractorError, StructuredOutputExtractor
from src.models.llm import DirectReasoningResponse
from src.models.test_case import LogicTestCase

logger = logging.getLogger(__name__)


def load_dataset(filepath: Path) -> list[LogicTestCase]:
    dataset = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            dataset.append(LogicTestCase.model_validate(data))
    return dataset


def build_prompt(case: LogicTestCase) -> str:
    rules_block = ""
    for rule in case.rules:
        rule_dict = rule if isinstance(rule, dict) else rule.model_dump()
        rules_block += f"ID: {rule_dict['id']} | Rule: {rule_dict['text']}\n"

    prompt = (
        "You are an expert logical reasoning system. Analyze the following set of logical rules.\n\n"
        f"RULES:\n{rules_block}\n\n"
        "You MUST write your step-by-step logical deduction in the 'reasoning' JSON field FIRST.\n"
        "Inside your reasoning, explicitly write out:\n"
        "1. FACT: What are the initial given true/false states? (e.g., 'R1 says X is True')\n"
        "2. CHAIN: Apply implications step-by-step. (e.g., 'From R1 and R2, Y must be True')\n"
        "3. CONTRADICTION CHECK: Compare derived states with TERMINAL rules. (e.g., 'R3 requires not Y, which contradicts our derivation')\n"
        "4. CONCLUSION: State clearly if there is a contradiction or not.\n\n"
        "Only AFTER writing this detailed reasoning, set 'is_sat' to true or false. "
        "If there is a contradiction, you must put the exact IDs of the conflicting rules (e.g., ['R1', 'R2', 'R3']) in the 'conflict_core' list."
    )
    return prompt


def evaluate_dataset(
    dataset: list[LogicTestCase],
    extractor: StructuredOutputExtractor,
    limit: int | None = None,
) -> dict[str, Any]:
    correct_sat = 0
    correct_mus = 0
    total = len(dataset) if limit is None else min(limit, len(dataset))

    results = []

    for i, case in enumerate(dataset[:limit]):
        logger.info("=" * 60)
        logger.info("PROCESSING CASE %d/%d (ID: %s)", i + 1, total, case.case_id)
        logger.info("=" * 60)

        prompt = build_prompt(case)
        logger.info("PROMPT SENT TO LLM:\n%s", prompt)

        try:
            response = extractor.extract(prompt, DirectReasoningResponse)

            is_sat_correct = response.is_sat == case.is_satisfiable
            if is_sat_correct:
                correct_sat += 1

            is_mus_correct = False
            if not case.is_satisfiable and not response.is_sat:
                expected_mus = set(case.mus_expected)
                actual_mus = set(response.conflict_core)
                is_mus_correct = expected_mus == actual_mus
                if is_mus_correct:
                    correct_mus += 1

            logger.info("PARSED RESPONSE Reasoning: %s", response.reasoning)
            sat_status = "CORRECT" if is_sat_correct else "WRONG"
            logger.info(
                "Predicted SAT: %s | Expected SAT: %s -> [%s]",
                response.is_sat,
                case.is_satisfiable,
                sat_status,
            )

            if not case.is_satisfiable and not response.is_sat:
                mus_status = "CORRECT" if is_mus_correct else "WRONG"
                logger.info(
                    "Predicted MUS: %s | Expected MUS: %s -> [%s]",
                    response.conflict_core,
                    case.mus_expected,
                    mus_status,
                )

            results.append(
                {
                    "case_id": case.case_id,
                    "expected_sat": case.is_satisfiable,
                    "predicted_sat": response.is_sat,
                    "is_sat_correct": is_sat_correct,
                    "expected_mus": case.mus_expected,
                    "predicted_mus": response.conflict_core,
                    "is_mus_correct": is_mus_correct,
                    "reasoning": response.reasoning,
                }
            )

        except ExtractorError as e:
            logger.error("ERROR processing case %s: %s", case.case_id, e)
            results.append({"case_id": case.case_id, "error": str(e)})

    unsat_total = sum(1 for c in dataset[:limit] if not c.is_satisfiable)

    metrics = {
        "total_cases": total,
        "sat_accuracy": correct_sat / total if total > 0 else 0.0,
        "mus_exact_match": correct_mus / unsat_total if unsat_total > 0 else 0.0,
    }

    return {"metrics": metrics, "details": results}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=str, default="data/generated_cases")
    parser.add_argument(
        "--model-name", type=str, default="openai/qwen2.5-coder-14b-instruct"
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-file", type=str, default="evaluation_results.json")
    args = parser.parse_args()

    dataset_path = Path(args.dataset_dir) / ManifestFilename.DATASET_JSONL.value
    if not dataset_path.exists():
        logger.error("Dataset not found at %s", dataset_path)
        return

    dataset = load_dataset(dataset_path)
    extractor = StructuredOutputExtractor(model_name=args.model_name)

    logger.info("Starting evaluation with model: %s", args.model_name)
    logger.info(
        "Using API Base: %s", os.environ.get("OPENAI_API_BASE", "Default (OpenAI)")
    )

    evaluation_report = evaluate_dataset(dataset, extractor, limit=args.limit)

    logger.info("=" * 50)
    logger.info("EVALUATION METRICS")
    logger.info("=" * 50)
    logger.info(
        "SAT Accuracy:    %.2f%%", evaluation_report["metrics"]["sat_accuracy"] * 100
    )
    logger.info(
        "MUS Exact Match: %.2f%%", evaluation_report["metrics"]["mus_exact_match"] * 100
    )
    logger.info("=" * 50)

    output_path = Path(args.dataset_dir) / args.output_file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evaluation_report, f, indent=2, ensure_ascii=False)

    logger.info("Full report saved to %s", output_path)


if __name__ == "__main__":
    main()
