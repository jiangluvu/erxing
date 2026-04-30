FROM python:3.12-slim

# Install system dependencies
RUN apt-get update -qq && apt-get install -y -qq ffmpeg && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose port
EXPOSE $PORT

# Start with gunicorn
CMD cd backend && gunicorn app:app --workers 1 --timeout 180 --bind 0.0.0.0:$PORT
