FROM python:3.9-slim

# Set the working directory
WORKDIR /app

RUN apt-get update \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Copy the source code and model files
COPY src/ ./src/
COPY data/models/ ./data/models/

# Set the command to run the main script
CMD ["python", "src/app.py"]

# Expose any necessary ports (if applicable)
# EXPOSE 8000