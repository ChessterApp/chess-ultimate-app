# Hermes for the load test (run_matrix.sh): Ubuntu's Python 3.12 and Stockfish, the CI requirements.
# Build from hermes/:  docker --context colima-loadtest build -t hermes-loadtest -f scripts/loadtest/Dockerfile .
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-dev git stockfish procps \
    ca-certificates build-essential && rm -rf /var/lib/apt/lists/*
COPY requirements-ci.txt /tmp/req.txt
RUN python3 -m venv /venv && /venv/bin/pip install -q --upgrade pip && /venv/bin/pip install -q -r /tmp/req.txt
ENV PATH=/venv/bin:/usr/games:$PATH
