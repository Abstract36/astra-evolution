from pathlib import Path

import pytest

from astra.config import Config, ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent


def test_default_yaml_mirrors_builtin_defaults():
    assert load_config(ROOT / "config" / "default.yaml").to_dict() == Config().to_dict()


@pytest.mark.parametrize("name", ["ollama.yaml", "owner.yaml", "deepseek.yaml", "router_vs_evolution.yaml", "hard_tasks.yaml"])
def test_shipped_configs_load(name):
    load_config(ROOT / "config" / name)


def test_overrides_are_parsed_as_yaml():
    cfg = load_config(None, ["evolution.mutation_rate=0.5", "experiment.arms=[evolving]", "market.shocks=[]"])
    assert cfg.evolution.mutation_rate == 0.5
    assert cfg.experiment.arms == ["evolving"]


def test_int_is_accepted_for_float_fields():
    cfg = load_config(None, ["economy.upkeep=2"])
    assert cfg.economy.upkeep == 2.0 and isinstance(cfg.economy.upkeep, float)


def test_nested_lists_build_dataclasses():
    cfg = load_config(None, ["market.shocks=[{generation: 3, category: automation, multiplier: 2}]"])
    assert cfg.market.shocks[0].category == "automation"


@pytest.mark.parametrize(
    "override, message",
    [
        ("evolution.mutation_rat=0.5", "unknown key"),
        ("economy.upkeep=lots", "expected float"),
        ("experiment.arms=[nonsense]", "unknown arm"),
        ("experiment.population_size=50", "max_population"),
        ("economy.initial_budget=1000", "owner_budget"),
        ("baseline.model=huge", "baseline.model"),
        ("market.shocks=[{generation: 1, category: nope, multiplier: 2}]", "unknown category"),
        ("broken", "section.key=value"),
        ("api.enabled=true", "max_api_spend_usd"),
    ],
)
def test_invalid_values_are_rejected(override, message):
    with pytest.raises(ConfigError, match=message):
        load_config(None, [override])
