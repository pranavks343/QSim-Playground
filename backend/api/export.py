# mypy: disable-error-code="no-untyped-call"
"""Export generators for completed runs.

Builds a runnable Jupyter notebook and a standalone Python script from a
finished run row. The script is dependency-free apart from numpy + qiskit
so reviewers can reproduce the QAOA setup without pulling in QSim.

The ``no-untyped-call`` ignore is module-scoped because ``nbformat.v4``
ships without inline type hints; we exercise it through tests and treat
the returned dict as ``Any``.
"""

from __future__ import annotations

import json
import textwrap
from typing import Any

import nbformat
from nbformat import v4 as nbf


def _winning_qubo(run: dict[str, Any]) -> dict[str, Any]:
    refined = run.get("refined_qubo")
    if isinstance(refined, dict):
        return refined
    winner = run.get("winner_agent")
    qubos = run.get("qubos")
    if isinstance(winner, str) and isinstance(qubos, dict):
        winner_qubo = qubos.get(winner)
        if isinstance(winner_qubo, dict):
            return winner_qubo
    raise ValueError("run has no winning QUBO to export")


def _matrix_literal(matrix: list[list[float]]) -> str:
    rows = []
    for row in matrix:
        cells = ", ".join(f"{value:.6f}" for value in row)
        rows.append(f"    [{cells}]")
    return "[\n" + ",\n".join(rows) + "\n]"


def _problem_summary(run: dict[str, Any]) -> str:
    problem_ir = run.get("problem_ir", {})
    name = problem_ir.get("name") or run.get("template") or "(unnamed)"
    description = problem_ir.get("description") or ""
    variables = problem_ir.get("variables") or []
    constraints = problem_ir.get("constraints") or []
    return textwrap.dedent(
        f"""\
        Problem name : {name}
        Description  : {description or '—'}
        Variables    : {len(variables)}
        Constraints  : {len(constraints)}
        """
    )


def _provenance_block(run: dict[str, Any]) -> str:
    qubo = _winning_qubo(run)
    winner_agent = run.get("winner_agent") or qubo.get("agent_name") or "(unknown)"
    critic = run.get("critic_verdict") or {}
    rationale = critic.get("rationale") or "(rationale unavailable)"
    confidence = critic.get("confidence") or "n/a"
    return textwrap.dedent(
        f"""\
        Winner agent    : {winner_agent}
        Critic confidence: {confidence}
        Critic rationale: {rationale}
        """
    )


def _benchmark_block(run: dict[str, Any]) -> str:
    sim = run.get("sim_result") or {}
    classical = run.get("classical_result") or {}
    if not sim and not classical:
        return "(benchmark data unavailable)"
    quality = sim.get("quality_vs_classical")
    quality_str = f"{quality:.1f}% of classical" if isinstance(quality, int | float) else "n/a"
    return textwrap.dedent(
        f"""\
        Classical (simulated annealing) best objective: {classical.get('best_objective')}
        Classical runtime                              : {classical.get('runtime_ms')} ms
        Quantum simulator best bitstring               : {sim.get('best_bitstring')}
        Quantum simulator best objective               : {sim.get('best_objective')}
        Quantum quality vs classical                   : {quality_str}
        """
    )


def build_notebook(run: dict[str, Any]) -> dict[str, Any]:
    """Return an nbformat-validated notebook JSON for the given run."""

    qubo = _winning_qubo(run)
    matrix = qubo.get("q_matrix") or []
    variable_order = qubo.get("variable_order") or []
    circuit = run.get("circuit_data") or {}
    qasm = circuit.get("qiskit_qasm") or ""
    notebook = nbf.new_notebook()
    notebook["metadata"] = {
        "language_info": {"name": "python", "version": "3.11"},
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "qsim_provenance": {
            "run_id": str(run.get("id") or ""),
            "winner_agent": run.get("winner_agent") or qubo.get("agent_name"),
        },
    }

    title = run.get("template") or run.get("problem_ir", {}).get("name") or "custom"
    intro_md = textwrap.dedent(
        f"""\
        # QSim Playground run — {title}

        Reproducible Jupyter export of a completed run. Install dependencies once:

        ```bash
        pip install numpy qiskit qiskit-aer
        ```

        ## Problem statement

        ```
        {_problem_summary(run).rstrip()}
        ```

        ## Why this formulation won

        ```
        {_provenance_block(run).rstrip()}
        ```
        """
    )
    notebook["cells"].append(nbf.new_markdown_cell(intro_md))

    ir_cell = (
        "# Normalised problem IR (Day 2 schema)\n"
        f"problem_ir = {json.dumps(run.get('problem_ir', {}), indent=2, sort_keys=True)}\n"
    )
    notebook["cells"].append(nbf.new_code_cell(ir_cell))

    matrix_cell = (
        "import numpy as np\n\n"
        f"variable_order = {variable_order!r}\n"
        f"Q = np.array({_matrix_literal(matrix)})\n"
        "print('Q shape:', Q.shape)\n"
    )
    notebook["cells"].append(nbf.new_code_cell(matrix_cell))

    notebook["cells"].append(
        nbf.new_markdown_cell(
            "## QAOA circuit\n\n"
            "Built from the refined QUBO matrix. The QASM below was emitted by Qiskit's\n"
            "transpiler during the original pipeline run; you can rebuild the circuit at\n"
            "runtime or simply import the QASM."
        )
    )

    qasm_cell_body = qasm.replace('"""', '\\"\\"\\"')
    qasm_cell = (
        "from qiskit import QuantumCircuit, qasm3\n\n"
        f'QASM_SOURCE = """{qasm_cell_body}"""\n\n'
        "circuit = qasm3.loads(QASM_SOURCE)\n"
        "print(circuit.draw(output='text', fold=120))\n"
    )
    notebook["cells"].append(nbf.new_code_cell(qasm_cell))

    sim_cell = textwrap.dedent(
        """\
        from qiskit_aer import AerSimulator
        from qiskit import transpile

        simulator = AerSimulator()
        compiled = transpile(circuit.measure_all(inplace=False), simulator)
        result = simulator.run(compiled, shots=1024).result()
        counts = result.get_counts()
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        print('Top-5 bitstrings (count desc):')
        for bitstring, shots in top:
            print(f'  {bitstring} : {shots}')
        """
    )
    notebook["cells"].append(nbf.new_code_cell(sim_cell))

    notebook["cells"].append(
        nbf.new_markdown_cell(
            "## Benchmark\n\n"
            "The classical simulated-annealing baseline is captured at run time so the\n"
            "quality-vs-classical figure stays honest.\n\n"
            f"```\n{_benchmark_block(run).rstrip()}\n```"
        )
    )

    nbformat.validate(notebook)
    return dict(notebook)


def build_script(run: dict[str, Any]) -> str:
    """Return a standalone, dependency-light Python script for the run."""

    qubo = _winning_qubo(run)
    matrix = qubo.get("q_matrix") or []
    variable_order = qubo.get("variable_order") or []
    winner_agent = run.get("winner_agent") or qubo.get("agent_name") or "(unknown)"
    strategy = qubo.get("strategy") or ""
    critic = run.get("critic_verdict") or {}
    rationale = critic.get("rationale") or ""
    benchmark = _benchmark_block(run).rstrip()
    qasm = run.get("circuit_data", {}).get("qiskit_qasm") or ""
    safe_qasm = qasm.replace('"""', '\\"\\"\\"')

    header_lines = [
        '"""QSim Playground export — runnable reproduction.',
        "",
        f"Run id        : {run.get('id') or '(unknown)'}",
        f"Winner agent  : {winner_agent}",
        f"Strategy      : {strategy.strip()}",
    ]
    if rationale.strip():
        rationale_lines = textwrap.wrap(f"Critic        : {rationale.strip()}", width=88)
        header_lines.extend(rationale_lines)
    header_lines.extend(
        [
            "",
            "This script depends only on numpy + qiskit + qiskit-aer. It rebuilds the",
            "QAOA circuit from the QASM emitted during the original run and prints the",
            "top-5 bitstrings from a 1024-shot simulation.",
            '"""',
        ]
    )
    header = "\n".join(header_lines)

    body = textwrap.dedent(
        """\
        from __future__ import annotations

        import numpy as np
        from qiskit import QuantumCircuit, qasm3, transpile
        from qiskit_aer import AerSimulator
        """
    )

    matrix_block = (
        f"VARIABLE_ORDER = {variable_order!r}\n" f"Q = np.array({_matrix_literal(matrix)})\n"
    )

    qasm_block = f'QASM_SOURCE = """{safe_qasm}"""\n'

    main_block = textwrap.dedent(
        """\
        def main() -> None:
            print('Q matrix shape:', Q.shape)
            print('Variable order:', VARIABLE_ORDER)

            circuit: QuantumCircuit = qasm3.loads(QASM_SOURCE)
            print(circuit.draw(output='text', fold=120))

            simulator = AerSimulator()
            compiled = transpile(circuit.measure_all(inplace=False), simulator)
            result = simulator.run(compiled, shots=1024).result()
            counts = result.get_counts()
            top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
            print('Top-5 bitstrings (count desc):')
            for bitstring, shots in top:
                print(f'  {bitstring} : {shots}')


        if __name__ == '__main__':
            main()
        """
    )

    benchmark_block = (
        '"""Reference benchmark from the original pipeline run.\n\n' f"{benchmark}\n" '"""\n'
    )

    return "\n\n".join([header, body, matrix_block, qasm_block, main_block, benchmark_block])


def export_filename(run: dict[str, Any], extension: str) -> str:
    """Build a filesystem-safe filename for the export."""

    name = run.get("template") or run.get("problem_ir", {}).get("name") or "qsim-run"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(name))
    run_id = str(run.get("id") or "anon")[:8]
    return f"qsim_{safe}_{run_id}.{extension}"
