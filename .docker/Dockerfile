FROM python:3.13-slim-bullseye

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    tini \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv and expose it to PATH
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Create virtual environment and activate it globally
RUN uv venv /venv
ENV PATH="/venv/bin:$PATH"
ENV PYTHONFAULTHANDLER=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy project files and install dependencies from lockfile
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen

# Copy the rest of the code
COPY . /app

EXPOSE 8000
