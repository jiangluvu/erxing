FROM python:3.12-slim

# Install system dependencies (ffmpeg + Node.js for frontend build)
RUN apt-get update -qq && apt-get install -y -qq ffmpeg curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Build frontend
RUN cd frontend && npm install && npm run build

# Expose port
EXPOSE $PORT

# Start with gunicorn
CMD cd backend && gunicorn app:app --workers 1 --timeout 180 --bind 0.0.0.0:$PORT
