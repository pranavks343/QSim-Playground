import numpy as np

name = "portfolio"
description = "Select exactly three assets while trading off expected return against risk."
x = np.array([0, 0, 0, 0, 0, 0])
returns = np.array([0.08, 0.11, 0.13, 0.09, 0.15, 0.12])
covariance = np.array(
    [
        [0.021, 0.004, 0.006, 0.003, 0.008, 0.005],
        [0.004, 0.030, 0.009, 0.005, 0.011, 0.007],
        [0.006, 0.009, 0.045, 0.006, 0.014, 0.010],
        [0.003, 0.005, 0.006, 0.018, 0.007, 0.004],
        [0.008, 0.011, 0.014, 0.007, 0.050, 0.012],
        [0.005, 0.007, 0.010, 0.004, 0.012, 0.035],
    ]
)
risk_weight = 1.0
return_weight = 2.0
objective = risk_weight * (x.T @ covariance @ x) - return_weight * (returns @ x)
select_exactly_three_assets = np.sum(x) == 3
metadata = {
    "template": "portfolio",
    "returns": [0.08, 0.11, 0.13, 0.09, 0.15, 0.12],
    "covariance": [
        [0.021, 0.004, 0.006, 0.003, 0.008, 0.005],
        [0.004, 0.030, 0.009, 0.005, 0.011, 0.007],
        [0.006, 0.009, 0.045, 0.006, 0.014, 0.010],
        [0.003, 0.005, 0.006, 0.018, 0.007, 0.004],
        [0.008, 0.011, 0.014, 0.007, 0.050, 0.012],
        [0.005, 0.007, 0.010, 0.004, 0.012, 0.035],
    ],
    "risk_weight": 1.0,
    "return_weight": 2.0,
    "expected_optimal_value": -0.5980000000000001,
}
minimize(objective)  # type: ignore[name-defined]  # noqa: F821
