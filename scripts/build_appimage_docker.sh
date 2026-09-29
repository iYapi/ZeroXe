#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Building Portable AppImage inside Ubuntu 22.04 Container (GLIBC 2.35)..."

CONTAINER_TOOL="docker"
if ! command -v docker >/dev/null 2>&1; then
    if command -v podman >/dev/null 2>&1; then
        CONTAINER_TOOL="podman"
    else
        echo "[Error] Neither docker nor podman found. Please install Docker to build portable AppImages."
        exit 1
    fi
fi

IMAGE_NAME="zeroxe-builder:ubuntu22.04"

echo "==> 1. Building Container Image..."
${CONTAINER_TOOL} build -f "${PROJECT_ROOT}/docker/Dockerfile.build" -t "${IMAGE_NAME}" "${PROJECT_ROOT}"

echo "==> 2. Extracting Compiled AppImage Artifact..."
mkdir -p "${PROJECT_ROOT}/dist"
${CONTAINER_TOOL} run --rm -v "${PROJECT_ROOT}/dist:/app/dist" "${IMAGE_NAME}"

echo "=================================================="
echo "Portable AppImage Build Finished!"
echo "Location: ${PROJECT_ROOT}/dist/Zeroxe-x86_64.AppImage"
echo "Compatible with: Ubuntu 22.04+, Debian 12+, Fedora, Arch, RHEL/Rocky"
echo "=================================================="
