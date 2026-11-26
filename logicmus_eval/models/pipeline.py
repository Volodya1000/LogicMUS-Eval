from pydantic import BaseModel

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

    def acceptance(self, threshold: float = 0.55) -> LeakageAcceptance:
        if not 0.5 <= threshold <= 1.0:
            raise ValueError("leakage_threshold must be between 0.5 and 1.0")
        metrics = {"global.word": self.global_word, "global.char": self.global_char}
        for size, analyzers in self.by_mus_size.items():
            metrics.update(
                {f"{size}.{name}": value for name, value in analyzers.items()}
            )
        failures = []
        for name, metric in metrics.items():
            score = metric.mean_balanced_accuracy
            if metric.status != "ok" or score is None:
                failures.append(
                    f"{name}: unavailable ({metric.reason or metric.status})"
                )
            elif score > threshold:
                failures.append(f"{name}: {score:.4f} > {threshold:.4f}")
        return LeakageAcceptance(
            threshold=threshold, passed=not failures, failures=failures
        )
