FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .
# -u: unbuffered output, so the agent's log appears immediately in docker compose logs
ENTRYPOINT ["python", "-u", "agent.py"]
