FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
COPY tests/ ./tests/
COPY registry/ ./registry/
COPY examples/ ./examples/
COPY README.md LICENSE ./

RUN pip install --no-cache-dir -e . pytest

CMD ["prompt-registry", "demo"]
