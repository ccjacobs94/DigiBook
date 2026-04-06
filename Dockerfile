FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg cdparanoia && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Persist library and data across restarts
VOLUME ["/app/library", "/app/data"]

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
