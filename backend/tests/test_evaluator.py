from __future__ import annotations

import math

import numpy as np
from test_agents.helpers import (
    decomp_output,
    domain_output,
    graph_output,
    penalty_output,
    slack_output,
)

from core.evaluator import (
    Scorecard,
    build_comparison_table,
    compute_condition_number,
    compute_penalty_sensitivity,
    compute_sparsity,
    evaluate_qubo,
    run_classical_baseline,
)
from core.templates import get_template, list_templates


def test_sparsity_identifies_dense_and_sparse_matrices() -> None:
    dense = np.ones((3, 3))
    sparse = np.diag([1.0, 0.0, 0.0])

    assert compute_sparsity(dense) == 0.0
    assert compute_sparsity(sparse) == 5 / 6


def test_condition_number_handles_singular_matrix() -> None:
    singular = np.array([[1.0, 2.0], [2.0, 4.0]])

    assert math.isinf(compute_condition_number(singular))


def test_penalty_sensitivity_returns_zero_without_lambda() -> None:
    ir = get_template("max_cut")
    qubo = graph_output(ir)

    assert compute_penalty_sensitivity(qubo, ir) == 0.0


def test_composite_score_is_bounded_for_all_agents_on_all_templates() -> None:
    metadata_by_name = {metadata.name: metadata for metadata in list_templates()}
    generators = [penalty_output, slack_output, graph_output, decomp_output, domain_output]

    for template_name in ["portfolio", "max_cut", "knapsack"]:
        ir = get_template(template_name)
        metadata = metadata_by_name[template_name]
        for generator in generators:
            scorecard = evaluate_qubo(generator(ir), ir, metadata)

            assert 0.0 <= scorecard.composite_score <= 10.0
            assert scorecard.qubit_count >= len(ir.variables)
            assert scorecard.notes


def test_comparison_table_sorts_by_composite_score() -> None:
    low = Scorecard(
        agent_name="low",
        qubit_count=3,
        sparsity=0.1,
        condition_number=10.0,
        penalty_sensitivity=0.2,
        classical_baseline_objective=1.0,
        classical_baseline_runtime_ms=1.0,
        composite_score=2.0,
        notes="low score",
    )
    high = low.model_copy(update={"agent_name": "high", "composite_score": 8.0})
    mid = low.model_copy(update={"agent_name": "mid", "composite_score": 5.0})

    table = build_comparison_table({"low": low, "high": high, "mid": mid})

    assert [scorecard.agent_name for scorecard in table.scorecards] == ["high", "mid", "low"]
    assert table.top_agent == "high"
    assert table.runner_up == "mid"


def test_classical_baseline_returns_objective_and_runtime_for_known_templates() -> None:
    for template_name in ["portfolio", "max_cut", "knapsack"]:
        qubo = penalty_output(get_template(template_name))
        objective, runtime_ms = run_classical_baseline(np.asarray(qubo.q_matrix, dtype=float))

        assert math.isfinite(objective)
        assert runtime_ms >= 0.0
