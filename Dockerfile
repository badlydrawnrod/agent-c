FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Include git for version info if needed, though strictly not required for runtime unless the tool uses git
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy dependency definition to cache dependencies
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project --no-dev

# Copy the project
COPY . .

# Install the project
RUN uv sync --frozen --no-dev

# Place the virtual environment in the path
ENV PATH="/app/.venv/bin:$PATH"

# Set the working directory for the user's workspace
WORKDIR /workspace

# Default entrypoint
ENTRYPOINT ["agent-c"]
