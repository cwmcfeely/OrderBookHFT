# Use the official Python base image
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of your application code
COPY . /app/

# Expose the port your app runs on
EXPOSE 8000

# Start the application
CMD ["python3", "-m", "api.server"]