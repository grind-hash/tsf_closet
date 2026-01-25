# LiteLLM Proxy Dockerfile
FROM ghcr.io/berriai/litellm:main-latest

# Copy configuration file
COPY docker/litellm/config.yaml /app/config.yaml

# Expose port 4000
EXPOSE 4000

# Run LiteLLM Proxy with config
CMD ["--config", "/app/config.yaml", "--host", "0.0.0.0", "--port", "4000"]
