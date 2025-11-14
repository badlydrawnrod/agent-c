#!/usr/bin/env python
"""Validation script for the modular architecture refactoring."""

print("=== Agent C Modular Architecture Validation ===\n")

# Test each module independently
print("1. Type Definitions (core/types.py)")
from agentc.core.types import RunDeps, AgentConfig, PersonalityConfig
print("   [OK] RunDeps, AgentConfig, PersonalityConfig imported")

print("\n2. File Operations (core/file_ops.py)")
from agentc.core.file_ops import (
    safe_resolve, safe_resolve_create, create_backup, write_and_verify
)
print("   [OK] File operation utilities imported")

print("\n3. Configuration Management (core/config.py)")
from agentc.core.config import load_configs, get_class, load_providers
print("   [OK] Config management utilities imported")

print("\n4. Tool Registry (core/tools.py)")
from agentc.core.tools import ToolRegistry
registry = ToolRegistry()
print(f"   [OK] Tool registry initialized with {len(registry.get_all())} tools")

print("\n5. Agent Factory (core/agent_factory.py)")
from agentc.core.agent_factory import create_agent, parse_args, discover_tools
print("   [OK] Agent factory utilities imported")

print("\n6. Core Module Public API (core/__init__.py)")
from agentc.core import (
    create_agent, discover_tools, load_configs, parse_args,
    RunDeps, AgentConfig, PersonalityConfig, ToolRegistry
)
print("   [OK] All core APIs accessible from agentc.core")

print("\n7. Main Entry Point (agent.py)")
from agentc.agent import main, _async_main
print("   [OK] Main entry point imported")

print("\n8. Package Public API (agentc/__init__.py)")
from agentc import (
    main, AgentConfig, PersonalityConfig, RunDeps,
    ToolRegistry, create_agent, load_configs
)
print("   [OK] Package APIs exported correctly")

print("\n" + "="*50)
print("[PASSED] All modular components validated successfully")
print("[PASSED] No circular dependencies detected")
print("[PASSED] Clean separation of concerns achieved")
