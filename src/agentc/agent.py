import argparse
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage
import tomllib


# ---- UTILITY FUNCTIONS ----


def safe_resolve(path_str: str) -> Path:
    """Safely resolve a path within the current working directory."""
    p = Path(path_str)
    base_dir = Path.cwd()
    try:
        resolved = (base_dir / p).resolve(strict=True)
    except FileNotFoundError:
        raise ValueError("Path does not exist.")
    except Exception as e:
        raise ValueError(f"Invalid path: {e}")
    if not resolved.is_relative_to(base_dir):
        raise ValueError("Path is outside the allowed directory.")
    return resolved


def safe_resolve_create(path_str: str) -> Path:
    """Safely resolve a path for creation within the current working directory."""
    p = Path(path_str)
    base_dir = Path.cwd()
    try:
        resolved = (base_dir / p).resolve()
    except Exception as e:
        raise ValueError(f"Invalid path: {e}")
    if not resolved.is_relative_to(base_dir):
        raise ValueError("Path is outside the allowed directory.")
    return resolved


def get_class(class_path: str) -> type:
    """Dynamically import and return the class based on its full path."""
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise ValueError(f"Could not import class from {class_path}: {e}")


# ---- DATA MODELS ----


class AgentConfig(BaseModel):
    """Configuration for an agent provider."""

    provider_cls: Any
    model_cls: Any
    api_key_env: str | None = None
    base_url: str | None = None
    model_name: str


class PersonalityConfig(BaseModel):
    """Configuration for an agent personality."""

    provider: str
    model: str | None = None
    prompt_file: str
    description: str


# ---- TOOL DEFINITIONS ----


def read_file(ctx: RunContext[Any], path: str) -> str:
    """Read the contents of a file."""
    resolved_path = safe_resolve(path)
    if not resolved_path.is_file():
        raise ValueError("Path must be a file.")
    return resolved_path.read_text()


def list_files(ctx: RunContext[Any], path: str) -> str:
    """List files in the specified directory."""
    resolved_path = safe_resolve(path)
    if not resolved_path.is_dir():
        raise ValueError("Path must be a directory.")
    return "\n".join(sorted(p.name for p in resolved_path.iterdir()))


def edit_file(ctx: RunContext[Any], path: str, old_str: str, new_str: str) -> str:
    """Edit a file by replacing old_str with new_str."""
    resolved_path = safe_resolve(path)
    if not resolved_path.is_file():
        raise ValueError("Path must be a file.")
    content = resolved_path.read_text()
    if old_str not in content:
        raise ValueError("old_str not found")
    new_content = content.replace(old_str, new_str)
    resolved_path.write_text(new_content)
    return "Edit completed"


def create_file(ctx: RunContext[Any], path: str, content: str) -> str:
    """Create a new file with the given content, creating parent directories if needed."""
    resolved_path = safe_resolve_create(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(content)
    return "File created"


def search_files(ctx: RunContext[Any], path: str, query: str) -> str:
    """Recursively search for a query string in files within a given path."""
    resolved_path = safe_resolve(path)
    if not resolved_path.is_dir():
        raise ValueError("Path must be a directory.")
    results = []
    for file_path in resolved_path.rglob("*"):
        if file_path.is_file():
            with file_path.open(encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if query in line:
                        results.append(f"{file_path}:{line_num}: {line.strip()}")
    return "\n".join(results)


async def delegate_to_agent(ctx: RunContext[Any], personality: str, task: str) -> str:
    """Delegate a task to another agent personality."""
    agent_configs, personalities = load_configs()
    if personality not in personalities:
        raise ValueError(f"Unknown personality: {personality}")
    print(f"--- Delegating to {personality}...")
    agent = create_agent(personality, personalities, agent_configs)
    result = await agent.run(task)
    print(f"--- Delegation result: {result.output}")
    return result.output


# Create tool instances.
tools = [
    Tool(read_file, takes_ctx=True, strict=True),
    Tool(list_files, takes_ctx=True, strict=True),
    Tool(edit_file, takes_ctx=True, strict=True),
    Tool(create_file, takes_ctx=True, strict=True),
    Tool(search_files, takes_ctx=True, strict=True),
    Tool(delegate_to_agent, takes_ctx=True, strict=True),
]


# ---- CONFIGURATION LOADING ----


def load_providers() -> dict:
    """Load providers configuration from providers.toml."""
    with open("providers.toml", "rb") as f:
        return tomllib.load(f)


def load_config_overrides() -> dict:
    """Load configuration overrides from config.toml."""
    try:
        with open("config.toml", "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def load_personalities_data() -> dict:
    """Load personalities configuration from personalities.toml."""
    try:
        with open("personalities.toml", "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def build_agent_configs(
    providers_data: dict, config_data: dict
) -> Dict[str, AgentConfig]:
    """Build agent configurations by merging providers and overrides."""
    agent_configs = {}
    for agent_type, data in providers_data.items():
        provider_config = AgentConfig(
            provider_cls=get_class(data["provider_cls"]),
            model_cls=get_class(data["model_cls"]),
            api_key_env=data.get("api_key_env"),
            base_url=data.get("base_url"),
            model_name=data["model_name"],
        )

        if agent_type in config_data:
            user_config = config_data[agent_type]
            provider_config.api_key_env = user_config.get(
                "api_key_env", provider_config.api_key_env
            )
            provider_config.base_url = user_config.get(
                "base_url", provider_config.base_url
            )
            provider_config.model_name = user_config.get(
                "model_name", provider_config.model_name
            )

        agent_configs[agent_type] = provider_config

    return agent_configs


def build_personalities(personalities_data: dict) -> Dict[str, PersonalityConfig]:
    """Build personalities configuration."""
    personalities = {}
    for personality_name, data in personalities_data.items():
        personalities[personality_name] = PersonalityConfig(**data)

    return personalities


def load_configs() -> tuple[Dict[str, AgentConfig], Dict[str, PersonalityConfig]]:
    """Load agent configurations and personalities."""
    providers = load_providers()
    overrides = load_config_overrides()
    personalities_data = load_personalities_data()
    agent_configs = build_agent_configs(providers, overrides)
    personalities = build_personalities(personalities_data)
    return agent_configs, personalities


# ---- AGENT CREATION ----


def validate_personality(
    personality_name: str,
    personalities: Dict[str, PersonalityConfig],
    agent_configs: Dict[str, AgentConfig],
) -> tuple[PersonalityConfig, AgentConfig]:
    """Validate personality and return config objects."""
    if personality_name not in personalities:
        raise ValueError(f"Unsupported personality: {personality_name}")
    personality = personalities[personality_name]
    if personality.provider not in agent_configs:
        raise ValueError(f"Unsupported provider: {personality.provider}")
    config = agent_configs[personality.provider]
    return personality, config


def build_provider(config: AgentConfig) -> Any:
    """Build the provider instance with necessary kwargs."""
    if config.api_key_env and not os.environ.get(config.api_key_env):
        raise ValueError(
            f"{config.api_key_env} environment variable is required for provider."
        )
    provider_kwargs = {}
    if config.api_key_env:
        provider_kwargs["api_key"] = os.environ.get(config.api_key_env)
    if config.base_url:
        provider_kwargs["base_url"] = config.base_url
    return config.provider_cls(**provider_kwargs)


def build_model(
    config: AgentConfig,
    personality: PersonalityConfig,
    model_override: str | None,
    provider: Any,
) -> Any:
    """Build the model instance."""
    model_name = model_override or personality.model or config.model_name
    return config.model_cls(model_name, provider=provider)


def load_system_prompt(personality: PersonalityConfig) -> str:
    """Load the system prompt from file."""
    with open(personality.prompt_file, "r") as f:
        return f.read()


def build_delegation_info(
    personality_name: str, personalities: Dict[str, PersonalityConfig]
) -> str:
    """Build delegation instructions."""
    return (
        "\n\nDelegation Instructions:\nYou can delegate tasks to other personalities using the delegate_to_agent tool if the task better fits their expertise.\n\nAvailable personalities:\n"
        + "\n".join(
            f"- {name}: {config.description}"
            for name, config in personalities.items()
            if name != personality_name
        )
    )


def parse_args(personalities: Dict[str, PersonalityConfig]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the agent with different personalities."
    )
    parser.add_argument(
        "--personality",
        choices=list(personalities.keys()),
        default="coder",
        help="Personality to use (default: coder)",
    )
    parser.add_argument(
        "--model",
        help="Override the default model for the selected personality",
    )
    return parser.parse_args()


def create_agent(
    personality_name: str,
    personalities: Dict[str, PersonalityConfig],
    agent_configs: Dict[str, AgentConfig],
    model_override: str | None = None,
) -> Agent:
    """Create an agent based on the specified personality."""
    personality, config = validate_personality(
        personality_name, personalities, agent_configs
    )
    provider = build_provider(config)
    model = build_model(config, personality, model_override, provider)
    system_prompt = load_system_prompt(personality) + build_delegation_info(
        personality_name, personalities
    )
    return Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )


def discover_tools() -> str:
    """Discover and format information about available tools."""
    return "\n".join(f"- {tool.name}: {tool.description}" for tool in tools)


# ---- MAIN EXECUTION ----


def main() -> None:
    """Main entry point of the application."""
    # Load config from TOML.
    agent_configs, personalities = load_configs()

    args = parse_args(personalities)
    try:
        agent = create_agent(args.personality, personalities, agent_configs, args.model)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    tools_info = discover_tools()
    print(
        f"I'm Agent C, a helpful coding agent.\n\nYou can ask me to perform various code editing tasks using the available tools:\n{tools_info}\n"
    )

    conversation: List[ModelMessage] = []
    while True:
        try:
            user_input = input("You: ")
            if user_input.strip().lower() in ("bye", "exit", "quit"):
                break
            result: AgentRunResult = agent.run_sync(
                user_input, message_history=conversation
            )
            print("Agent C:", result.output)
            conversation = result.new_messages()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
