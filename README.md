# QSim Playground

[![CI](https://github.com/pranavks343/QSim-Playground/actions/workflows/ci.yml/badge.svg)](https://github.com/pranavks343/QSim-Playground/actions/workflows/ci.yml)

QSim Playground is a multi-agent quantum optimization sandbox for ML engineers.

## Status

Day 2 agent pipeline work is complete.

## Quickstart

```bash
cd backend
python -m pip install -r requirements.txt
python -m pip install -e .
```

List the built-in templates:

```bash
qsim list-templates
```

Load a template as normalized IR JSON:

```bash
qsim load --template portfolio
```

Parse a supported NumPy snippet:

```bash
qsim parse --file tests/fixtures/portfolio_numpy.py
```

Validate an IR JSON file:

```bash
qsim load --template knapsack > /tmp/knapsack_ir.json
qsim validate --file /tmp/knapsack_ir.json
```

Run the full local pipeline:

```bash
qsim run --template portfolio
```

Example output excerpt:

```text
QSim Pipeline
portfolio
Variables: 6 | Constraints: 1 | Run: cli-...

Agent Formulations
Comparison
Rank  Agent    Score  Qubits  Sparsity  Condition  Sensitivity
1     decomp   7.212  6       0.000     2.78       0.000
2     graph    6.947  6       0.000     2.37       0.000

Critic Verdict
decomp wins with composite_score=7.212...

Refiner Improvements
- none — original was already near-optimal

Simulation Results
Best bitstring: 111110
Objective: -0.4476
Quality vs classical: 100.00%

Execution Comparison
Classical / Simulator / Hardware (Day 6+)
Total wall-clock: 0.62s
```

## Planned Features

- Normalized optimization problem IR.
- Portfolio, Max-Cut, and Knapsack templates.
- AST-only parser for supported NumPy snippets.
- Multi-agent QUBO, circuit, evaluation, critique, and refinement pipeline.
- FastAPI backend with Supabase auth, RLS, quotas, rate limits, and realtime traces.
- Next.js frontend for inputs, agent traces, benchmarks, and exports.

## Built in 5 Days

This project is being built from a focused 5-day implementation plan.

## License

MIT. See [LICENSE](LICENSE).
