FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the frontend code
COPY . .

# BACKEND_URL is overridden by docker-compose.yml for container-to-container
# networking (e.g. http://backend:8000); defaults to localhost for standalone use.
ENV BACKEND_URL=http://localhost:8000

EXPOSE 8501

# --server.address=0.0.0.0 is required so the app is reachable from outside the container
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
