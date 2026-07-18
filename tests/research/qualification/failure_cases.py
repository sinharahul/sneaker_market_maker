from tests.research.qualification.fixtures import (
    ARTIFACT_HASH,
    POLICY_VERSION,
    evaluation_report,
    historical_override,
    interval,
)

BLOCKING_CASES = [
    ({"historical_reports": (evaluation_report(), evaluation_report())}, "required_folds"),
    (
        historical_override("net_return", interval(0.005, spread=0.01)),
        "net_return_lower_vs_deterministic",
    ),
    (
        historical_override("ce_vs_heuristic", interval(0.001, spread=0.01)),
        "ce_vs_heuristic_lower",
    ),
    (historical_override("cvar", interval(0.04, spread=0.02)), "cvar_ceiling"),
    (
        historical_override("max_drawdown", interval(0.08, spread=0.05)),
        "drawdown_ceiling",
    ),
    (
        historical_override("inventory_age", interval(12.0, spread=3.0)),
        "inventory_age_ceiling",
    ),
    (
        historical_override("stranded_inventory", interval(0.01, spread=0.02)),
        "stranded_inventory_ceiling",
    ),
    (
        historical_override("capital_utilization", interval(0.55, spread=0.20)),
        "capital_utilization_ceiling",
    ),
    (
        historical_override("turnover_rate", interval(0.10, spread=0.05)),
        "turnover_floor",
    ),
    (
        historical_override("gate_rejection_rate", interval(0.02, spread=0.04)),
        "gate_rejection_ceiling",
    ),
    (
        {"historical_reports": (evaluation_report(support_coverage=0.90),) * 3},
        "support_coverage",
    ),
    (
        {
            "historical_reports": (
                evaluation_report(
                    seed_results={1: {"net_return": 0.01}, 2: {"net_return": 0.05}},
                ),
                evaluation_report(),
                evaluation_report(),
            )
        },
        "seed_dispersion",
    ),
    (
        {
            "stress_reports": (
                evaluation_report(
                    metrics={
                        "max_drawdown": interval(0.25, spread=0.01),
                        "cvar": interval(0.06),
                    },
                    historical=False,
                ),
            )
        },
        "stress_drawdown_ceiling",
    ),
    (
        {
            "stress_reports": (
                evaluation_report(
                    metrics={
                        "max_drawdown": interval(0.10),
                        "cvar": interval(0.10, spread=0.01),
                    },
                    historical=False,
                ),
            )
        },
        "stress_cvar_ceiling",
    ),
    ({"shadow_observations": 500}, "shadow_observations"),
    ({"shadow_stream_hash_match": False}, "paper_stream_equivalent"),
    (
        {"drill_results": {"restart": False, "rollback": True, "drift": True, "artifact": True}},
        "restart_drill",
    ),
    (
        {"drill_results": {"restart": True, "rollback": False, "drift": True, "artifact": True}},
        "rollback_drill",
    ),
    (
        {"drill_results": {"restart": True, "rollback": True, "drift": False, "artifact": True}},
        "drift_drill",
    ),
    (
        {"drill_results": {"restart": True, "rollback": True, "drift": True, "artifact": False}},
        "artifact_drill",
    ),
]

APPROVAL_REJECTION_CASES = [
    ({"shadow_observations": 0}, "valid confirmation"),
    ({}, "missing hash and version"),
    ({}, f"artifact {ARTIFACT_HASH} only"),
    (
        {},
        (
            f"I approve advisory use for artifact {ARTIFACT_HASH} "
            f"under benchmark policy {POLICY_VERSION}"
        ),
    ),
]
