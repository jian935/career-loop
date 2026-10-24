FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CAREER_LOOP_DB=/data/loop.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY career_loop ./career_loop
RUN pip install --no-cache-dir .

COPY data ./data
COPY examples ./examples

VOLUME ["/data"]

ENTRYPOINT ["career-loop"]
CMD ["--help"]
