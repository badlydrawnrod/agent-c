"""Pydantic_AI-specific type aliases."""

from __future__ import annotations

from pydantic_ai import Agent, DeferredToolRequests

from ...deps import RunDeps


# Alias for the configured pydantic_ai Agent used by this backend.
NextAgent = Agent[RunDeps, str | DeferredToolRequests]

__all__ = ["NextAgent"]
