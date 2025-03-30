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
COPY uv.lock pyproject.toml /app/
COPY event_distributor/pyproject.toml /app/event_distributor/
COPY state_manager/pyproject.toml /app/state_manager/
COPY websocket_service/pyproject.toml /app/websocket_service/


RUN uv sync --all-packages --frozen --no-cache

COPY . /app

RUN mkdir -p /app/logs
ENV LOG_DIR=/app/logs CONFIG_PATH=/config.yaml

ENTRYPOINT [ "/app/.venv/bin/uvicorn", "--port", "80", "--host", "0.0.0.0" ]
