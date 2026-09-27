from typer.testing import CliRunner

from logicmus_eval.cli import app

runner = CliRunner()


def test_generate_invalid_mus_size():
    result = runner.invoke(
        app, ["generate", "--mus-size-min", "5", "--mus-size-max", "3"]
    )
    assert result.exit_code != 0
    assert "mus-size-min cannot be greater than mus-size-max" in result.output


def test_generate_mus_size_exceeds_total_rules():
    result = runner.invoke(
        app, ["generate", "--mus-size-max", "30", "--total-rules", "20"]
    )
    assert result.exit_code != 0
    assert "mus-size-max cannot be greater than total-rules" in result.output


def test_evaluate_invalid_strategy():
    result = runner.invoke(app, ["evaluate", "--strategy", "invalid"])
    assert result.exit_code != 0
    assert "strategy must be 'direct' or 'z3'" in result.output
