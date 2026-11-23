FROM python:3.12-slim
WORKDIR /app

# Install Python dependencies first for faster Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all 9 modular Python files into the container
COPY *.py .
EXPOSE 8000

# -u disables output buffering so logs appear immediately in docker compose logs
ENTRYPOINT ["python", "-u", "central.py"]
