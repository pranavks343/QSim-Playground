from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cli.main import app
from core.ir import ProblemIR
from core.templates import get_template

RUNNER = CliRunner()
FIXTURE_DIR = Path(__file__).parent / "fixtures"


def json_from_output(output: str) -> dict[str, object]:
    data = json.loads(output)
    assert isinstance(data, dict)
    return data


def test_load_each_template_outputs_valid_ir_json() -> None:
    for template_name in ["portfolio", "max_cut", "knapsack"]:
        result = RUNNER.invoke(app, ["load", "--template", template_name])

        assert result.exit_code == 0
        data = json_from_output(result.stdout)
        assert ProblemIR.from_dict(data).to_dict() == get_template(template_name).to_dict()


def test_load_unknown_template_exits_one() -> None:
    result = RUNNER.invoke(app, ["load", "--template", "missing"])

    assert result.exit_code == 1
    assert "template not found" in result.stderr


def test_parse_fixture_file_succeeds() -> None:
    result = RUNNER.invoke(app, ["parse", "--file", str(FIXTURE_DIR / "portfolio_numpy.py")])

    assert result.exit_code == 0
    data = json_from_output(result.stdout)
    assert ProblemIR.from_dict(data).name == "portfolio"


def test_parse_malformed_file_exits_one(tmp_path: Path) -> None:
    source_file = tmp_path / "bad.py"
    source_file.write_text("x = np.array([0, 1]\nobjective = x", encoding="utf-8")

    result = RUNNER.invoke(app, ["parse", "--file", str(source_file)])

    assert result.exit_code == 1
    assert "parse failed" in result.stderr
    assert "syntax error" in result.stderr


def test_list_templates_shows_exactly_three_template_rows() -> None:
    result = RUNNER.invoke(app, ["list-templates"])

    assert result.exit_code == 0
    assert result.stdout.count("portfolio") == 1
    assert result.stdout.count("max_cut") == 1
    assert result.stdout.count("knapsack") == 1


def test_validate_accepts_valid_ir_json(tmp_path: Path) -> None:
    ir_file = tmp_path / "portfolio.json"
    ir_file.write_text(get_template("portfolio").to_json(), encoding="utf-8")

    result = RUNNER.invoke(app, ["validate", "--file", str(ir_file)])

    assert result.exit_code == 0
    assert "valid" in result.stdout


def test_validate_rejects_malformed_ir_json(tmp_path: Path) -> None:
    ir_file = tmp_path / "bad.json"
    ir_file.write_text(json.dumps({"name": "bad"}), encoding="utf-8")

    result = RUNNER.invoke(app, ["validate", "--file", str(ir_file)])

    assert result.exit_code == 1
    assert "invalid" in result.stderr
