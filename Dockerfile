FROM python:3.12

RUN pip3 install cmake && \
  git clone https://github.com/herumi/mcl.git && \
  cd mcl && \
  mkdir build && \
  cd build && \
  cmake .. && \
  make -j8 && \
  make install

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install the application dependencies.
WORKDIR /app

# Copy the application into the container.
COPY pyproject.toml uv.lock /app/

RUN uv sync --frozen --no-cache

# Copy the application into the container.
COPY . /app

RUN mkdir -p /app/logs
ENV LOG_DIR=/app/logs CONFIG_PATH=/config.yaml

CMD ["/app/.venv/bin/uvicorn", "--no-access-log", "--port", "80", "--host", "0.0.0.0", "app.main:app"]
