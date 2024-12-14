FROM python:3.12

RUN pip3 install cmake && \
  git clone https://github.com/herumi/mcl.git && \
  cd mcl && \
  mkdir build && \
  cd build && \
  cmake .. && \
  make -j8 && \
  make install

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  # Poetry's configuration:
  POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_CREATE=false \
  POETRY_CACHE_DIR='/var/cache/pypoetry' \
  POETRY_HOME='/usr/local' \
  POETRY_VERSION=1.8.3

WORKDIR /zex
COPY pyproject.toml poetry.lock ./
RUN curl -sSL https://install.python-poetry.org | python3 - && /usr/local/bin/poetry install
COPY . .
RUN /usr/local/bin/poetry install

EXPOSE 15782
CMD ["python", "app/main.py", "/config.yaml"]
