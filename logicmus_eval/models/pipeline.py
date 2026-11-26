from pydantic import BaseModel, Field

from logicmus_eval.models.manifests import LeakageAcceptance, TfidfMetrics


class DatasetValidationMetrics(BaseModel):
    sat_valid: int = 0
    unsat_valid: int = 0
    mus_valid: int = 0
    mus_minimal: int = 0


class LeakageReport(BaseModel):
    global_word: TfidfMetrics
    global_char: TfidfMetrics
    by_mus_size: dict[str, dict[str, TfidfMetrics]]
    by_input: dict[str, dict[str, dict[str, TfidfMetrics]]] = Field(
        default_factory=dict
    )

    def acceptance(
        self,
        threshold: float = 0.55,
        mus_sizes: list[int] | None = None,
        required_inputs: tuple[str, ...] = (),
    ) -> LeakageAcceptance:
        if not 0.5 <= threshold <= 1.0:
            raise ValueError("leakage_threshold must be between 0.5 and 1.0")
        failures = []
        required_groups = (
            {f"mus_size={k}" for k in mus_sizes}
            if mus_sizes is not None
            else set(self.by_mus_size)
        )
        if not required_groups:
            failures.append("Missing per-K measurements")
        for name in required_inputs:
            if name not in self.by_input:
                failures.append(f"Missing input-view measurements: {name}")
        primary = {
            "global": {"word_tfidf": self.global_word, "char_tfidf": self.global_char},
            **self.by_mus_size,
        }
        for view, groups in {"primary": primary, **self.by_input}.items():
            for group in sorted(required_groups | {"global"}):
                for analyzer in ("word_tfidf", "char_tfidf"):
                    metric = groups.get(group, {}).get(analyzer)
                    name = f"{view}.{group}.{analyzer}"
                    if metric is None or not metric.is_measured:
                        failures.append(f"{name}: unavailable or invalid measurements")
                    elif (
                        metric.mean_balanced_accuracy is not None
                        and metric.mean_balanced_accuracy > threshold
                    ):
                        failures.append(
                            f"{name}: {metric.mean_balanced_accuracy:.4f} > {threshold:.4f}"
                        )
        return LeakageAcceptance(
            threshold=threshold, passed=not failures, failures=failures
        )
