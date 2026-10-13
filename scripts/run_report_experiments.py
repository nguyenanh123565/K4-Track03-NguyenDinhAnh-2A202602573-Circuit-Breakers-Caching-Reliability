"""Reproduce report experiments without changing the submission configuration."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gameday_lab.client import ResilientClient
from gameday_lab.factory import build_client
from gameday_lab.sim.config import load_config
from gameday_lab.sim.engine import run_scenario


class UnfilteredExperimentClient(ResilientClient):
    """Negative control for capability filtering; never used by the factory."""

    def ladder(self, task: str) -> list[str]:
        return list(self.order)


def main() -> None:
    results = {}
    base = load_config("configs/gameday.yaml", "configs/scenarios.yaml")
    cache_base = load_config("configs/gameday.yaml", "configs/scenarios_cache.yaml")
    variants = []
    for enabled in (True, False):
        cfg = copy.deepcopy(base)
        cfg.client["breaker"]["min_calls"] = 1000000000
        cfg.client["max_attempts_per_provider"] = 5
        if not enabled:
            cfg.client.update(retry_budget_ratio=100, retry_budget_max_tokens=1e9,
                              retry_budget_min_per_s=1e6)
        variants.append(("budget_on" if enabled else "budget_off", cfg,
                         ["G2_overload_storm", "G3_brownout"], "resilient"))
    cfg = copy.deepcopy(base)
    cfg.client["attempt_timeout_s"] = 30
    variants.append(("timeout_30", cfg, ["G4_slow_region", "G6_provider_outage"], "resilient"))
    variants.append(("unfiltered", copy.deepcopy(base), ["G6_provider_outage"], "unfiltered"))
    for parameter, values in (("similarity_threshold", [0.80, 0.92, 0.97]),
                              ("ttl_s", [30, 60, 300]), ("max_stale_s", [0])):
        for value in values:
            cfg = copy.deepcopy(cache_base)
            cfg.cache[parameter] = value
            variants.append((f"cache_{parameter}_{value}", cfg, ["C1_faq_outage"], "cached"))
    for name, cfg, scenarios, client_name in variants:
        results[name] = {"client": cfg.client, "cache": cfg.cache, "seed": 25, "runs": {}}
        for scenario in scenarios:
            client = (UnfilteredExperimentClient(cfg.provider_infos(), cfg.fallback_order, cfg.client, seed=1)
                      if client_name == "unfiltered" else build_client(client_name, cfg))
            sim = run_scenario(cfg, scenario, client, 25)
            metrics = sim.metrics()
            results[name]["runs"][scenario] = metrics
            print(name, scenario, json.dumps({k: metrics[k] for k in (
                "availability", "latency_p95_s", "amplification", "retry_ratio", "recovery_s",
                "give_up_reasons", "incompatible_routes")}), flush=True)
            if "wrong_answers" in metrics:
                print({k: metrics[k] for k in ("wrong_answers", "wrong_answers_by_reason",
                      "outdated_answers", "faq_availability", "cache_hit_ratio", "cost_per_good_turn")}, flush=True)
    Path("reports/experiments.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
