FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No CMD here on purpose — docker-compose.yml sets a different `command:`
# per service (api runs uvicorn, worker runs arq, migrate runs alembic),
# all from this same image, so we only build it once.
