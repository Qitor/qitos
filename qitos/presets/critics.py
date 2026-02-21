"""Critic presets."""

from __future__ import annotations

from qitos.core.critic import PassThroughCritic


def pass_through_critic() -> PassThroughCritic:
    return PassThroughCritic()


__all__ = ["pass_through_critic"]
