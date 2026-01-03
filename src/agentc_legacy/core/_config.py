"""Configuration file discovery and loading for Agent C.

This module provides centralized handling of TOML file location and loading,
eliminating duplication across multiple loader functions.
"""

import tomllib
from pathlib import Path


class ConfigLocator:
    """Centralized configuration file discovery and loading.

    Handles finding and loading TOML configuration files from both the package
    directory and current working directory, with fallback support.
    """

    def __init__(self) -> None:
        """Initialize locator with package and working directories."""
        self.package_dir = Path(__file__).parent.parent
        self.cwd = Path.cwd()

    def load_file(self, filename: str, fallback_to_cwd: bool = False) -> dict:
        """Load TOML file from package directory, optionally falling back to cwd.

        Args:
            filename: Name of TOML file (e.g., 'providers.toml').
            fallback_to_cwd: If True, try current working directory if package file not found.

        Returns:
            Dictionary of loaded TOML data.

        Raises:
            FileNotFoundError: If file not found in package dir and fallback disabled.
        """
        package_path = self.package_dir / filename

        # Try package directory first
        try:
            with open(package_path, "rb") as f:
                return tomllib.load(f)
        except FileNotFoundError:
            if not fallback_to_cwd:
                raise

            # Try current working directory as fallback
            cwd_path = self.cwd / filename
            try:
                with open(cwd_path, "rb") as f:
                    return tomllib.load(f)
            except FileNotFoundError:
                return {}

    def load_providers(self) -> dict:
        """Load providers.toml from package directory.

        Returns:
            Dictionary of provider configurations.

        Raises:
            FileNotFoundError: If providers.toml not found.
        """
        return self.load_file("providers.toml", fallback_to_cwd=False)

    def load_personalities(self) -> dict:
        """Load personalities.toml from package directory.

        Returns:
            Dictionary of personality configurations, empty dict if not found.
        """
        return self.load_file("personalities.toml", fallback_to_cwd=False)

    def load_config_overrides(self) -> dict:
        """Load config.toml with fallback from package to cwd.

        Returns:
            Dictionary of configuration overrides, empty dict if not found.
        """
        return self.load_file("config.toml", fallback_to_cwd=True)
