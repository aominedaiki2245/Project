# Stage 1: Builder
FROM python:3.11-alpine AS builder

# Install build dependencies
RUN apk add --no-cache gcc musl-dev linux-headers postgresql-dev tzdata

# Set timezone
ENV TZ=Europe/Moscow

WORKDIR /app

# Copy and install requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-alpine

# Install runtime dependencies only (if any, but minimal for Alpine)
RUN apk add --no-cache tzdata

# Set timezone
ENV TZ=Europe/Moscow

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY bot.py .
COPY package.json .  # If not needed, remove this line

# Create non-root user
RUN adduser -D -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

# Run the bot
CMD ["python", "-u", "bot.py"]
