# Ollama Dockerfile - GPU enabled
FROM ollama/ollama:latest

# Copy entrypoint script
COPY docker/ollama/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Ollama API port
EXPOSE 11434

# Use custom entrypoint to pull models on startup
ENTRYPOINT ["/entrypoint.sh"]
