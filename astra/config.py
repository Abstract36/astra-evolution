"""Typed configuration: defaults, YAML loading and ``section.key=value`` overrides.

Every field has a default, so a YAML file only needs the values it changes.
``config/default.yaml`` mirrors these defaults one-to-one (a test enforces it).
"""

from __future__ import annotations

import dataclasses
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

# Experiment arms: name -> (initial strategies, evolution enabled).
ARMS: dict[str, tuple[str, bool]] = {
    "evolving": ("random", True),
    "static_random": ("random", False),
    "static_tuned": ("tuned", False),
    "evolving_tuned": ("tuned", True),
    "router": ("menu", False),  # a learning router over a fixed menu of strategies (see router.py)
}


class ConfigError(ValueError):
    """Raised when a configuration file or override is invalid."""


@dataclass
class ExperimentConfig:
    name: str = "first_evolution"
    generations: int = 100
    seeds: int = 10
    base_seed: int = 1
    population_size: int = 20
    arms: list[str] = field(
        default_factory=lambda: ["evolving", "static_random", "static_tuned", "evolving_tuned"]
    )
    results_dir: str = "results"
    save_ledger: bool = False


@dataclass
class CategorySpec:
    name: str
    demand: float = 0.2
    pay_rate: float = 2.0
    difficulty: float = 0.5


@dataclass
class ShockSpec:
    generation: int
    category: str
    multiplier: float


def _default_categories() -> list[CategorySpec]:
    return [
        CategorySpec("software_dev", demand=0.30, pay_rate=2.6, difficulty=0.60),
        CategorySpec("data_processing", demand=0.25, pay_rate=1.8, difficulty=0.40),
        CategorySpec("automation", demand=0.20, pay_rate=2.2, difficulty=0.50),
        CategorySpec("market_research", demand=0.15, pay_rate=2.0, difficulty=0.45),
        CategorySpec("digital_products", demand=0.10, pay_rate=2.4, difficulty=0.55),
    ]


@dataclass
class MarketConfig:
    tasks_per_generation: int = 120
    agent_capacity: int = 5
    size_range: list[float] = field(default_factory=lambda: [1.0, 5.0])
    demand_drift: float = 0.1
    internal_competition: bool = False
    external_competition: bool = True
    competitor_price_range: list[float] = field(default_factory=lambda: [0.6, 1.0])
    competitor_reputation: float = 0.6
    shocks: list[ShockSpec] = field(default_factory=list)
    categories: list[CategorySpec] = field(default_factory=_default_categories)


@dataclass
class ModelSpec:
    name: str
    quality: float = 0.7
    cost_per_unit: float = 1.0


def _default_models() -> list[ModelSpec]:
    return [
        ModelSpec("small", quality=0.62, cost_per_unit=0.35),
        ModelSpec("medium", quality=0.75, cost_per_unit=0.90),
        ModelSpec("large", quality=0.88, cost_per_unit=2.20),
    ]


@dataclass
class EconomyConfig:
    initial_budget: float = 100.0
    upkeep: float = 1.0
    initial_reputation: float = 0.5
    reputation_alpha: float = 0.2
    bid_cost: float = 0.1
    review_cost_overhead: float = 0.35
    cost_noise: float = 0.1
    success_sharpness: float = 10.0


@dataclass
class AgentSettings:
    min_focus_to_bid: float = 0.05
    prior_success: float = 0.6
    prior_weight: float = 2.0
    prior_win_rate: float = 0.5
    exploration_trials: int = 2


@dataclass
class EvolutionConfig:
    defund_after: int = 4
    cull_fraction: float = 0.1
    fitness_window: int = 3
    spawn_cost: float = 5.0
    child_endowment: float = 25.0
    parent_reserve: float = 20.0
    payback_generations: float = 15.0
    reinvest_returned: bool = False
    target_unserved: bool = False  # children are built to take the unserved work of their niche
    tournament_size: int = 3
    crossover_rate: float = 0.3
    mutation_rate: float = 0.3
    mutation_scale: float = 0.15
    reputation_inheritance: float = 0.5
    memory_inheritance: float = 0.5


@dataclass
class BaselineConfig:
    """Fixed strategy for the ``*_tuned`` arms: one specialist per slot.

    The defaults are the best of 360 combinations found by grid search on
    tuning seeds 101-103, which never appear in the evaluation (base_seed 1).
    """

    model: str = "medium"
    effort: float = 0.75
    price_level: float = 0.8
    max_difficulty: float = 0.65
    min_confidence: float = 0.45
    review: bool = False


@dataclass
class RouterConfig:
    """The menu of the ``router`` arm: every category x model x effort x price level x review."""

    efforts: list[float] = field(default_factory=lambda: [0.75, 1.25])
    price_levels: list[float] = field(default_factory=lambda: [0.6, 0.9])
    review: list[bool] = field(default_factory=lambda: [False])
    difficulty_bands: int = 4  # success rates are learned per category and per band of task difficulty


@dataclass
class SandboxConfig:
    max_population: int = 20
    max_spawns_per_generation: int = 6
    owner_budget: float = 2000.0
    allowed_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost", "::1"])
    request_timeout: float = 300.0
    max_tokens_per_call: int = 4096
    max_api_spend_usd: float = 0.0  # real money; 0 means no paid API call is allowed


@dataclass
class VerifiableCategory:
    name: str
    base_price: float = 4.0
    demand: float = 0.25


def _default_verifiable() -> list[VerifiableCategory]:
    return [
        VerifiableCategory("arithmetic"),
        VerifiableCategory("sorting"),
        VerifiableCategory("counting"),
        VerifiableCategory("extraction"),
    ]


@dataclass
class OllamaConfig:
    enabled: bool = True
    host: str = "http://127.0.0.1:11434"
    models: list[str] = field(default_factory=list)
    max_model_size_gb: float = 10.0
    cost_per_second: float = 0.5
    temperature: float = 0.2
    think: bool = False
    base_tokens: int = 256
    owner_tokens: int = 1500
    categories: list[VerifiableCategory] = field(default_factory=_default_verifiable)


@dataclass
class APIModelSpec:
    """A paid model and its prices in USD per million tokens."""

    name: str
    input_usd_per_mtok: float = 0.3
    cached_input_usd_per_mtok: float = 0.006
    output_usd_per_mtok: float = 1.2


def _default_api_models() -> list[APIModelSpec]:
    return [APIModelSpec("deepseek-flash", 0.3, 0.006, 1.2)]


@dataclass
class APIConfig:
    """An OpenAI-compatible chat API (DeepSeek by default). Off unless enabled."""

    enabled: bool = False
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    credits_per_usd: float = 1000.0
    thinking_tokens: int = 1024  # extra output budget when an agent's effort turns thinking on
    models: list[APIModelSpec] = field(default_factory=_default_api_models)


@dataclass
class Config:
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    models: list[ModelSpec] = field(default_factory=_default_models)
    economy: EconomyConfig = field(default_factory=EconomyConfig)
    agent: AgentSettings = field(default_factory=AgentSettings)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    api: APIConfig = field(default_factory=APIConfig)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def validate(self) -> Config:
        exp, sandbox = self.experiment, self.sandbox
        unknown = [a for a in exp.arms if a not in ARMS]
        if unknown:
            raise ConfigError(f"experiment.arms: unknown arm(s) {unknown}; choose from {list(ARMS)}")
        if exp.generations < 1 or exp.seeds < 1:
            raise ConfigError("experiment.generations and experiment.seeds must be >= 1")
        if not 1 <= exp.population_size <= sandbox.max_population:
            raise ConfigError(
                f"experiment.population_size={exp.population_size} must be between 1 and "
                f"sandbox.max_population={sandbox.max_population}"
            )
        needed = exp.population_size * self.economy.initial_budget
        if needed > sandbox.owner_budget:
            raise ConfigError(
                f"initial funding {needed:g} (population_size x initial_budget) exceeds "
                f"sandbox.owner_budget={sandbox.owner_budget:g}"
            )
        names = [m.name for m in self.models]
        if not names or len(set(names)) != len(names):
            raise ConfigError("models: need at least one model and unique names")
        if any(ARMS[a][0] == "tuned" for a in exp.arms) and self.baseline.model not in names:
            raise ConfigError(f"baseline.model={self.baseline.model!r} is not one of models {names}")
        categories = [c.name for c in self.market.categories]
        if not categories or any(c.demand <= 0 for c in self.market.categories):
            raise ConfigError("market.categories: need at least one category, all with demand > 0")
        for shock in self.market.shocks:
            if shock.category not in categories:
                raise ConfigError(f"market.shocks: unknown category {shock.category!r}")
        if len(self.market.size_range) != 2 or len(self.market.competitor_price_range) != 2:
            raise ConfigError("market.size_range and market.competitor_price_range need two numbers")
        if self.api.enabled and self.sandbox.max_api_spend_usd <= 0:
            raise ConfigError("api.enabled needs sandbox.max_api_spend_usd > 0 (a cap on real spending)")
        if not 0 <= self.evolution.cull_fraction < 1:
            raise ConfigError("evolution.cull_fraction must be in [0, 1)")
        return self


def load_config(path: str | Path | None = None, overrides: Iterable[str] = ()) -> Config:
    """Load ``path`` (optional) on top of the defaults, then apply ``key=value`` overrides."""
    data: dict[str, Any] = {}
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
        if loaded is not None and not isinstance(loaded, dict):
            raise ConfigError(f"{path}: the top level must be a mapping")
        data = loaded or {}
    for item in overrides:
        _apply_override(data, item)
    return config_from_dict(data)


def config_from_dict(data: dict[str, Any]) -> Config:
    return _build(Config, data, "config").validate()


def _apply_override(data: dict[str, Any], item: str) -> None:
    key, sep, raw = item.partition("=")
    if not sep or not key.strip():
        raise ConfigError(f"override must look like section.key=value, got {item!r}")
    parts = key.strip().split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise ConfigError(f"override {item!r}: {part!r} is not a section")
    node[parts[-1]] = yaml.safe_load(raw)


def _build(cls: type, data: Any, where: str) -> Any:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: expected a mapping, got {type(data).__name__}")
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = sorted(set(data) - names)
    if unknown:
        raise ConfigError(f"{where}: unknown key(s): {', '.join(unknown)}")
    hints = typing.get_type_hints(cls)
    kwargs = {name: _coerce(hints[name], value, f"{where}.{name}") for name, value in data.items()}
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise ConfigError(f"{where}: {exc}") from None


def _coerce(tp: Any, value: Any, where: str) -> Any:
    if dataclasses.is_dataclass(tp):
        return _build(tp, value, where)
    if typing.get_origin(tp) is list:
        if not isinstance(value, list):
            raise ConfigError(f"{where}: expected a list, got {value!r}")
        (item_type,) = typing.get_args(tp)
        return [_coerce(item_type, v, f"{where}[{i}]") for i, v in enumerate(value)]
    if tp is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if tp in (int, float, str, bool) and not isinstance(value, tp):
        raise ConfigError(f"{where}: expected {tp.__name__}, got {value!r}")
    return value
