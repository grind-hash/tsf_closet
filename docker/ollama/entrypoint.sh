#!/bin/bash
set -e

# Start Ollama server in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready (using ollama list instead of curl)
echo "Waiting for Ollama server to start..."
MAX_ATTEMPTS=30
ATTEMPT=0
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if ollama list > /dev/null 2>&1; then
        echo "Ollama server is ready!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo "Attempt $ATTEMPT/$MAX_ATTEMPTS - waiting..."
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "ERROR: Ollama server failed to start"
    exit 1
fi

# Pull required models
echo "========================================="
echo "Pulling gemma3:4b model..."
echo "========================================="
ollama pull gemma3:4b

echo "========================================="
echo "Pulling llava:7b model..."
echo "========================================="
ollama pull llava:7b

echo "========================================="
echo "Pulling gpt-oss:20b model..."
echo "========================================="
ollama pull gpt-oss:20b

echo "========================================="
echo "All models pulled successfully!"
echo "========================================="

# Keep the server running in foreground
wait $OLLAMA_PID
