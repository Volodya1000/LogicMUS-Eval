# Logical Benchmark Generator & Z3 Oracle Pipeline

Production-grade pipeline for generating paired SAT/UNSAT logical benchmarks with strict Z3 verification, minimal unsatisfiable subset (MUS) checks, and lexical leakage diagnostics.

## Structure
- `src/enums.py` - Typed StrEnum definitions.
- `src/models.py` - Dataclasses with serialization support.
- `src/templates.py` - Template packs and isolated predicate pools.
- `src/verifier.py` - Z3 logical oracle and MUS validator.
- `src/generator.py` - Deterministic shared-RNG benchmark generator.
- `tests/` - Comprehensive unit test suite.
- `run_pipeline.py` - Experiment orchestrator and manifest exporter.
