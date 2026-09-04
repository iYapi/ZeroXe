#!/usr/bin/env bash
set -e

# --- Configuration & Paths ---
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="zeroxe"
APP_DISPLAY_NAME="Zeroxe"
APP_DIR="${PROJECT_ROOT}/build/AppDir"
DIST_DIR="${PROJECT_ROOT}/dist"
APPIMAGE_TOOL="${PROJECT_ROOT}/build/appimagetool-x86_64.AppImage"
ICON_SOURCE="${PROJECT_ROOT}/assets/icons/zeroxe.png"

echo "==> Building AppImage for ${APP_DISPLAY_NAME}..."

# 1. Build PyInstaller in onedir mode via uv
echo "==> Compiling application via scripts/build_executable.py..."
cd "${PROJECT_ROOT}"
uv run python scripts/build_executable.py --onedir

# 2. Prepare clean AppDir layout
echo "==> Setting up AppDir directory tree..."
rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}/usr/bin"
mkdir -p "${APP_DIR}/usr/share/icons/hicolor/256x256/apps"

# 3. Copy compiled application files
echo "==> Copying application payload into AppDir..."
cp -r "${DIST_DIR}/${APP_NAME}/"* "${APP_DIR}/usr/bin/"

# 4. Set up the Application Icon
if [ -f "${ICON_SOURCE}" ]; then
    cp "${ICON_SOURCE}" "${APP_DIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
    cp "${ICON_SOURCE}" "${APP_DIR}/${APP_NAME}.png"
else
    echo "==> [Warning] No icon found at ${ICON_SOURCE}. Generating fallback placeholder..."
    # 256x256 dummy 1-pixel PNG fallback
    echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > "${APP_DIR}/${APP_NAME}.png"
    cp "${APP_DIR}/${APP_NAME}.png" "${APP_DIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
fi

# 5. Create Desktop Entry specification
echo "==> Generating desktop integration entry (${APP_NAME}.desktop)..."
cat <<EOF > "${APP_DIR}/${APP_NAME}.desktop"
[Desktop Entry]
Type=Application
Name=${APP_DISPLAY_NAME}
Comment=Cross-platform Python/PySide6 Desktop Application
Exec=${APP_NAME} %F
Icon=${APP_NAME}
Categories=Utility;Development;
Terminal=true
StartupNotify=true
EOF

# 6. Create the AppRun Entry Script
# Preserves CLI flags like --background and user script arguments
echo "==> Generating AppRun entrypoint..."
cat <<'EOF' > "${APP_DIR}/AppRun"
#!/usr/bin/env bash
SELF_DIR="$(dirname "$(readlink -f "${0}")")"
export PATH="${SELF_DIR}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${SELF_DIR}/usr/bin:${LD_LIBRARY_PATH}"

# Execute target binary while forwarding all terminal arguments
exec "${SELF_DIR}/usr/bin/zeroxe" "$@"
EOF
chmod +x "${APP_DIR}/AppRun"

# 7. Fetch appimagetool if not already present
if [ ! -f "${APPIMAGE_TOOL}" ]; then
    echo "==> Downloading appimagetool..."
    mkdir -p "$(dirname "${APPIMAGE_TOOL}")"
    curl -sLo "${APPIMAGE_TOOL}" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "${APPIMAGE_TOOL}"
fi

# 8. Package the final AppImage
echo "==> Assembling final AppImage binary..."
cd "${PROJECT_ROOT}"

# Disable embedded runtime fallback when building inside Docker or unprivileged containers
export ARCH=x86_64
"${APPIMAGE_TOOL}" --no-appstream "${APP_DIR}" "${DIST_DIR}/${APP_DISPLAY_NAME}-x86_64.AppImage"

echo "=================================================="
echo "AppImage build completed successfully!"
echo "Artifact: ${DIST_DIR}/${APP_DISPLAY_NAME}-x86_64.AppImage"
echo "=================================================="