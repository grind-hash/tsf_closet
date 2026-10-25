#!/bin/bash
set -e

cd /app/ComfyUI

# Model download URLs (Hugging Face)
# Note: Update these URLs if the models are hosted elsewhere
# GGUF (Q2_K) diffusion models are the default so that ~8 GB VRAM GPUs can run them.
# They are loaded by the ComfyUI-GGUF custom node installed in the Dockerfile.
DIFFUSION_GGUF_MODEL_URL="${DIFFUSION_GGUF_MODEL_URL:-https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q2_K.gguf}"
DIFFUSION_NSFW_GGUF_MODEL_URL="${DIFFUSION_NSFW_GGUF_MODEL_URL:-https://huggingface.co/Novice25/Qwen-Image-Edit-Rapid-AIO-GGUF/resolve/main/v23/Qwen-Rapid-NSFW-v23_Q2_K.gguf}"
DIFFUSION_MODEL_URL="${DIFFUSION_MODEL_URL:-https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors}"
DIFFUSION_NSFW_MODEL_URL="${DIFFUSION_NSFW_MODEL_URL:-https://huggingface.co/Phr00t/Qwen-Image-Edit-Rapid-AIO/resolve/main/v23/Qwen-Rapid-AIO-NSFW-v23.safetensors}"
TEXT_ENCODER_URL="${TEXT_ENCODER_URL:-https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors}"
VAE_URL="${VAE_URL:-https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors}"
LORA_URL="${LORA_URL:-https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors}"

# Function to download model if not exists
download_if_missing() {
    local url="$1"
    local dest="$2"
    
    if [ -f "$dest" ]; then
        echo "Model already exists: $dest"
    else
        echo "Downloading: $dest"
        curl -L --progress-bar -o "$dest" "$url"
        echo "Downloaded: $dest"
    fi
}

echo "=== Checking and downloading Qwen Image Edit 2511 models ==="

# Download diffusion models (GGUF, used by workflows/*_gguf.json)
download_if_missing "$DIFFUSION_GGUF_MODEL_URL" "models/diffusion_models/qwen-image-edit-2511-Q2_K.gguf"

download_if_missing "$DIFFUSION_NSFW_GGUF_MODEL_URL" "models/diffusion_models/Qwen-Rapid-NSFW-v23_Q2_K.gguf"

# Non-quantized diffusion models for GPUs with plenty of VRAM (used by the non-GGUF workflows).
# Uncomment to download them.
# download_if_missing "$DIFFUSION_MODEL_URL" "models/diffusion_models/qwen_image_edit_2511_bf16.safetensors"

# download_if_missing "$DIFFUSION_NSFW_MODEL_URL" "models/diffusion_models/Qwen-Rapid-AIO-NSFW-v23.safetensors"

# Download text encoder
download_if_missing "$TEXT_ENCODER_URL" "models/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"

# Download VAE
download_if_missing "$VAE_URL" "models/vae/qwen_image_vae.safetensors"

# Download LoRA
download_if_missing "$LORA_URL" "models/loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"

echo "=== All models ready ==="

# Start ComfyUI
echo "Starting ComfyUI..."
exec python main.py --listen 0.0.0.0 --port 8188
