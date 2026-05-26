import numpy as np

name = "knapsack"
description = "Choose a high-value subset of items without exceeding capacity."
x = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
values = np.array([24.0, 32.0, 50.0, 18.0, 60.0, 27.0, 38.0, 13.0, 31.0, 20.0])
weights = np.array([12.0, 18.0, 25.0, 9.0, 30.0, 14.0, 21.0, 7.0, 16.0, 11.0])
capacity_value = 100.0
objective = values @ x
capacity = weights @ x <= capacity_value
metadata = {
    "template": "knapsack",
    "items": [
        {"name": "calibrator", "weight": 12.0, "value": 24.0},
        {"name": "sensor", "weight": 18.0, "value": 32.0},
        {"name": "optimizer", "weight": 25.0, "value": 50.0},
        {"name": "compiler", "weight": 9.0, "value": 18.0},
        {"name": "sampler", "weight": 30.0, "value": 60.0},
        {"name": "validator", "weight": 14.0, "value": 27.0},
        {"name": "router", "weight": 21.0, "value": 38.0},
        {"name": "cache", "weight": 7.0, "value": 13.0},
        {"name": "monitor", "weight": 16.0, "value": 31.0},
        {"name": "exporter", "weight": 11.0, "value": 20.0},
    ],
    "capacity": 100.0,
    "expected_optimal_value": 196.0,
}
maximize(objective)  # type: ignore[name-defined]  # noqa: F821
