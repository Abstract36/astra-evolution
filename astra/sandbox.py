"""Hard limits set by the owner of a node.

Everything that consumes shared resources goes through these checks: how many
agents may exist, how many may be created per generation, how much owner money
may be allocated, and which hosts may be contacted over the network.

This version deliberately contains no code that copies agents to other
machines, contacts hosts outside ``allowed_hosts`` or moves real money.
Running on another device always means its owner installs and starts Astra
themselves.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from .config import SandboxConfig


class SandboxViolation(PermissionError):
    """An action exceeded a limit set by the owner."""


class Sandbox:
    def __init__(self, cfg: SandboxConfig):
        self.cfg = cfg

    @property
    def max_population(self) -> int:
        return self.cfg.max_population

    def check_population(self, current: int, adding: int = 1) -> None:
        if current + adding > self.cfg.max_population:
            raise SandboxViolation(
                f"population would reach {current + adding}, limit is {self.cfg.max_population}"
            )

    def check_spawn(self, spawned_this_generation: int) -> None:
        if spawned_this_generation >= self.cfg.max_spawns_per_generation:
            raise SandboxViolation(
                f"spawn limit of {self.cfg.max_spawns_per_generation} per generation reached"
            )

    def check_allocation(self, allocated: float, amount: float) -> None:
        if allocated + amount > self.cfg.owner_budget + 1e-9:
            raise SandboxViolation(
                f"owner budget exceeded: {allocated:g} already allocated, "
                f"{amount:g} requested, budget is {self.cfg.owner_budget:g}"
            )

    def check_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise SandboxViolation(f"unsupported URL scheme in {url!r}")
        host = parts.hostname or ""
        if host not in self.cfg.allowed_hosts:
            raise SandboxViolation(
                f"host {host!r} is not in sandbox.allowed_hosts {self.cfg.allowed_hosts}; "
                "add it only if you own that machine"
            )

    def clamp_tokens(self, tokens: int) -> int:
        return max(1, min(int(tokens), self.cfg.max_tokens_per_call))
