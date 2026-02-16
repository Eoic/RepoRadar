FROM python:3.11.11-slim

WORKDIR /app

# Install dependencies first (cached unless pyproject.toml changes)
COPY pyproject.toml .
RUN mkdir -p app && touch app/__init__.py && \
    pip install --no-cache-dir . && \
    rm -rf app

# Copy application code
COPY app/ app/
COPY scripts/ scripts/

RUN addgroup --system app && adduser --system --home /home/app --ingroup app app
USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
