FROM python:3.12-slim-bookworm AS base

# Install common dependencies
RUN apt update && apt install -y --no-install-recommends \
  git \
  pkg-config \
  libsecp256k1-dev \
  build-essential \
  gcc \
  libgmp-dev \
  automake \
  && apt clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# build some related tools
FROM base AS build

# Install cmake and dependencies
RUN apt update && apt install -y clang cmake && \
  git clone https://github.com/herumi/mcl.git && \
  cd mcl && \
  mkdir build && \
  cd build && \
  cmake -DCMAKE_CXX_COMPILER=clang++ .. && \
  make -j8 && \
  make install

# Final runtime image
FROM base AS runtime

# Copy the prebuilt mcl library
COPY --from=build /usr/local/lib /usr/local/lib
COPY --from=build /usr/local/include /usr/local/include


# Set a non-root user for security
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy the application into the container.
COPY uv.lock pyproject.toml /app/
COPY event_distributor/pyproject.toml /app/event_distributor/
COPY state_manager/pyproject.toml /app/state_manager/
COPY websocket_service/pyproject.toml /app/websocket_service/

# Install application dependencies
RUN uv sync --all-packages --frozen --no-cache

# Copy application files
COPY . /app

# Ensure logs directory exists and set permissions
# FIXME: After changing the log handler just in stdout we should remove this
# TODO: Add a volume for logs
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Set environment variables
ENV LOG_DIR=/app/logs CONFIG_PATH=/config.yaml

# Switch to non-root user
USER appuser

# Expose the necessary port
EXPOSE 80

# Run the application
ENTRYPOINT [ "/app/.venv/bin/uvicorn", "--port", "80", "--host", "0.0.0.0" ]
