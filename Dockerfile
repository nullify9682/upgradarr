FROM python:3.12-slim

# Installe requests
RUN pip install --no-cache-dir requests

# Non-root user
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY upgradarr.py .
RUN chown -R appuser:appuser /app
USER appuser

CMD ["python3", "upgradarr.py"]
