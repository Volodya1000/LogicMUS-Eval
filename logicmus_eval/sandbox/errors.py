"""Exceptions describing rejected generated programs and inconclusive checks."""


class ContractError(Exception):
    """The generated program does not implement the supported contract."""


class SolverUnknownError(Exception):
    """A required SMT check could not establish SAT or UNSAT."""
