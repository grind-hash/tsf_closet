# ComfyUI Dockerfile - Qwen Image Edit 2511
FROM nvidia/cuda:13.1.1-cudnn-runtime-ubuntu24.04
ARG PYTORCH_CUDA_TOOLKIT_URL
# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    python3-pip \
    git \
    curl \
    wget \
    libglx-mesa0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Clone ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

WORKDIR /app/ComfyUI

# Install PyTorch with CUDA support
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url ${PYTORCH_CUDA_TOOLKIT_URL-https://download.pytorch.org/whl/cu124}

# Install ComfyUI requirements
RUN pip install --no-cache-dir -r requirements.txt

# Create model directories
RUN mkdir -p models/diffusion_models \
    models/text_encoders \
    models/vae \
    models/loras

# Copy entrypoint script
COPY docker/comfyui/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose ComfyUI port
EXPOSE 8188

# Use custom entrypoint to download models on startup
ENTRYPOINT ["/entrypoint.sh"]
