"""Reproduce the turnover-scale sensitivity calculation.

The manuscript uses Q_it <= gamma * s_it. If s_it is multiplied by a
positive factor a, the same feasible turnover set is obtained with
gamma_new = gamma_primary / a.

This script reproduces the sensitivity values for 0.5x and 2x the
primary turnover scale from the reported thresholds.
"""

from csv import DictWriter
from pathlib import Path

PRIMARY = [
    {"R": 40, "relaxed": 0.0000, "exact": 0.0000},
    {"R": 60, "relaxed": 0.0067, "exact": 0.0182},
    {"R": 80, "relaxed": 0.0052, "exact": 0.0149},
    {"R": 100, "relaxed": 0.0062, "exact": 0.0161},
]

SCALE_MULTIPLIERS = {"0.5x": 0.5, "1.0x": 1.0, "2.0x": 2.0}


def rescaled_threshold(primary_threshold, multiplier):
    if multiplier <= 0:
        raise ValueError("The scale multiplier must be positive.")
    return primary_threshold / multiplier


def main():
    rows = []
    for item in PRIMARY:
        for label, multiplier in SCALE_MULTIPLIERS.items():
            rows.append({
                "R": item["R"],
                "scale": label,
                "relaxed_threshold": rescaled_threshold(item["relaxed"], multiplier),
                "exact_integer_threshold": rescaled_threshold(item["exact"], multiplier),
            })

    output = Path(__file__).with_name("turnover_scale_sensitivity_results.csv")
    with output.open("w", newline="") as f:
        writer = DictWriter(
            f,
            fieldnames=["R", "scale", "relaxed_threshold", "exact_integer_threshold"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {output}")
    print("R   scale   relaxed       exact")
    print("-" * 36)
    for row in rows:
        print(
            f'{row["R"]:3d} {row["scale"]:>5s} '
            f'{row["relaxed_threshold"]:10.5f} '
            f'{row["exact_integer_threshold"]:10.5f}'
        )


if __name__ == "__main__":
    main()
