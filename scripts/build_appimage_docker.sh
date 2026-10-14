#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

function show_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [DISTRO]

Compile ZeroXe into a standalone AppImage inside a Docker or Podman container.

Distro Choices:
  ubuntu22, ubuntu, 22    Ubuntu 22.04 LTS (GLIBC 2.35)
                          -> Recommended for production (runs on almost all Linux distributions)
  fedora42, fedora, 42    Fedora 42 (GLIBC 2.41+)
                          -> Modern toolchain for bleeding-edge systems (Fedora, Arch, etc.)

Options:
  -u, --ubuntu            Build using Ubuntu 22.04 LTS container
  -f, --fedora            Build using Fedora 42 container
  -d, --distro <name>     Specify target distribution (ubuntu22 or fedora42)
  --no-cache              Build Docker image without cache
  -h, --help              Show this help message and exit

Environment Variables:
  DISTRO=<name>           Preselect distro (e.g. DISTRO=fedora42)
  CONTAINER_TOOL=<tool>   Override container runtime (docker or podman)

Examples:
  $(basename "$0")                   # Interactive prompt (defaults to Ubuntu 22.04)
  $(basename "$0") ubuntu22          # Build via Ubuntu 22.04
  $(basename "$0") fedora42          # Build via Fedora 42
  $(basename "$0") -f --no-cache     # Rebuild Fedora 42 container from scratch
EOF
    exit 0
}

SELECTED_DISTRO="${DISTRO:-}"
EXTRA_BUILD_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            ;;
        -u|--ubuntu)
            SELECTED_DISTRO="ubuntu22"
            shift
            ;;
        -f|--fedora)
            SELECTED_DISTRO="fedora42"
            shift
            ;;
        -d|--distro)
            SELECTED_DISTRO="$2"
            shift 2
            ;;
        --distro=*)
            SELECTED_DISTRO="${1#*=}"
            shift
            ;;
        --no-cache)
            EXTRA_BUILD_ARGS+=("--no-cache")
            shift
            ;;
        ubuntu22|ubuntu|22|ubuntu-22|ubuntu-22.04)
            SELECTED_DISTRO="ubuntu22"
            shift
            ;;
        fedora42|fedora|42|fedora-42)
            SELECTED_DISTRO="fedora42"
            shift
            ;;
        *)
            echo "[Error] Unknown argument: $1"
            echo "Run '$(basename "$0") --help' for usage."
            exit 1
            ;;
    esac
done

# If no distro specified, ask interactively or default in non-interactive sessions
if [ -z "${SELECTED_DISTRO}" ]; then
    if [ -t 0 ]; then
        echo "=========================================================="
        echo "              ZeroXe Docker AppImage Compiler"
        echo "=========================================================="
        echo "Choose target distribution for AppImage compilation:"
        echo "  [1] Ubuntu 22.04 LTS (GLIBC 2.35 - Maximum portability) [Default]"
        echo "  [2] Fedora 42        (GLIBC 2.41+ - Modern Fedora environment)"
        echo "----------------------------------------------------------"
        read -rp "Enter choice [1-2] (default: 1): " choice
        case "${choice}" in
            2|fedora*|42)
                SELECTED_DISTRO="fedora42"
                ;;
            1|ubuntu*|22|"")
                SELECTED_DISTRO="ubuntu22"
                ;;
            *)
                echo "[Warning] Invalid choice '${choice}', defaulting to Ubuntu 22.04 LTS."
                SELECTED_DISTRO="ubuntu22"
                ;;
        esac
    elif read -t 0.1 -r choice 2>/dev/null && [ -n "${choice}" ]; then
        case "${choice}" in
            2|fedora*|42)
                SELECTED_DISTRO="fedora42"
                ;;
            1|ubuntu*|22|"")
                SELECTED_DISTRO="ubuntu22"
                ;;
            *)
                echo "[Warning] Invalid piped choice '${choice}', defaulting to Ubuntu 22.04 LTS."
                SELECTED_DISTRO="ubuntu22"
                ;;
        esac
    else
        echo "[Notice] Non-interactive session: defaulting to Ubuntu 22.04 LTS."
        SELECTED_DISTRO="ubuntu22"
    fi
fi

# Normalize distro selection
case "${SELECTED_DISTRO,,}" in
    ubuntu22|ubuntu|22|ubuntu-22|ubuntu-22.04)
        DISTRO_TAG="ubuntu22"
        DISTRO_NAME="Ubuntu 22.04 LTS (GLIBC 2.35)"
        DOCKERFILE="${PROJECT_ROOT}/docker/Dockerfile.ubuntu22"
        if [ ! -f "${DOCKERFILE}" ]; then
            DOCKERFILE="${PROJECT_ROOT}/docker/Dockerfile.build"
        fi
        IMAGE_NAME="zeroxe-builder:ubuntu22.04"
        COMPAT_NOTE="Ubuntu 22.04+, Debian 12+, Fedora 36+, Arch Linux, RHEL/Rocky 9+"
        ;;
    fedora42|fedora|42|fedora-42)
        DISTRO_TAG="fedora42"
        DISTRO_NAME="Fedora 42 (GLIBC 2.41+)"
        DOCKERFILE="${PROJECT_ROOT}/docker/Dockerfile.fedora42"
        IMAGE_NAME="zeroxe-builder:fedora42"
        COMPAT_NOTE="Fedora 42+, Arch Linux (Rolling), Ubuntu 25+, Cutting-edge distros"
        ;;
    *)
        echo "[Error] Unsupported distro '${SELECTED_DISTRO}'."
        echo "Allowed options: ubuntu22, fedora42"
        exit 1
        ;;
esac

if [ ! -f "${DOCKERFILE}" ]; then
    echo "[Error] Dockerfile not found at: ${DOCKERFILE}"
    exit 1
fi

# Detect container runtime (docker or podman)
if [ -z "${CONTAINER_TOOL}" ]; then
    if command -v docker >/dev/null 2>&1; then
        CONTAINER_TOOL="docker"
    elif command -v podman >/dev/null 2>&1; then
        CONTAINER_TOOL="podman"
    else
        echo "[Error] Neither docker nor podman found. Please install Docker or Podman to build portable AppImages."
        exit 1
    fi
fi

echo "=========================================================="
echo "==> Target Distribution: ${DISTRO_NAME}"
echo "==> Container Engine:    ${CONTAINER_TOOL}"
echo "==> Dockerfile:          ${DOCKERFILE}"
echo "==> Container Image:     ${IMAGE_NAME}"
echo "=========================================================="

echo "==> 1. Building Container Image..."
"${CONTAINER_TOOL}" build "${EXTRA_BUILD_ARGS[@]}" -f "${DOCKERFILE}" -t "${IMAGE_NAME}" "${PROJECT_ROOT}"

echo "==> 2. Extracting Compiled AppImage Artifact..."
mkdir -p "${PROJECT_ROOT}/dist"
"${CONTAINER_TOOL}" run --rm -e DISTRO_TAG="${DISTRO_TAG}" -v "${PROJECT_ROOT}/dist:/app/dist" "${IMAGE_NAME}"

echo "=========================================================="
echo "AppImage Build Finished Successfully!"
echo "Target Base: ${DISTRO_NAME}"
echo "Artifact Locations:"
echo "  - ${PROJECT_ROOT}/dist/Zeroxe-x86_64.AppImage"
echo "  - ${PROJECT_ROOT}/dist/Zeroxe-${DISTRO_TAG}-x86_64.AppImage"
echo "Target Compatibility:"
echo "  ${COMPAT_NOTE}"
echo "=========================================================="
