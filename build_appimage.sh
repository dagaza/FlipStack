#!/bin/bash
set -e  # Stop on error

# 1. SETUP PATHS
REPO_ROOT=$(pwd)
mkdir -p "$REPO_ROOT/bin"
if [ -f "$REPO_ROOT/linuxdeploy-root/AppRun" ]; then
    ln -sf "$REPO_ROOT/linuxdeploy-root/AppRun" "$REPO_ROOT/bin/linuxdeploy"
    ln -sf "$REPO_ROOT/linuxdeploy-plugin-python-root/AppRun" "$REPO_ROOT/bin/linuxdeploy-plugin-python"
fi
export PATH="$REPO_ROOT/bin:$PATH"

echo "✅ Tools setup in $REPO_ROOT/bin"

# 2. CLEANUP
rm -rf AppDir FlipStack*.AppImage

# 3. INSTALL APP
echo "📦 Installing dependencies..."
python3 -m pip install . --prefix="$REPO_ROOT/AppDir/usr" --break-system-packages

# 4. MANUALLY COPY ASSETS
SITE_PACKAGES=$(find AppDir -type d \( -name "site-packages" -o -name "dist-packages" \) | head -n 1)
cp -r assets "$SITE_PACKAGES/"

# 4.5 NORMALIZE FOLDER STRUCTURE
if [ -d "AppDir/usr/local/lib" ]; then
    echo "🔧 Normalizing directory structure..."
    mkdir -p AppDir/usr/lib
    cp -r AppDir/usr/local/lib/* AppDir/usr/lib/
    rm -rf AppDir/usr/local
fi

# 5. DESKTOP INTEGRATION
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp io.github.dagaza.FlipStack.desktop AppDir/usr/share/applications/
cp assets/icons/io.github.dagaza.FlipStack.svg AppDir/usr/share/icons/hicolor/scalable/apps/

# 6. FIX EXECUTABLE LOCATION
BINARY=$(find AppDir -name "flipstack" -type f | head -n 1)
mkdir -p AppDir/usr/bin
if [ "$BINARY" != "AppDir/usr/bin/flipstack" ]; then
    echo "🚚 Moving executable to AppDir/usr/bin/"
    mv "$BINARY" AppDir/usr/bin/
fi

# 6.5 PATCH THE SHEBANG
echo "🔧 Patching executable interpreter path..."
sed -i '1s|^#!.*|#!/usr/bin/env python3|' AppDir/usr/bin/flipstack

# 7. PATCH DESKTOP FILE
sed -i 's|^Exec=.*|Exec=flipstack|' AppDir/usr/share/applications/io.github.dagaza.FlipStack.desktop

export VERSION="1.0.0"
export LINUXDEPLOY_OUTPUT_VERSION="$VERSION"

# =========================================================
# PHASE 1: Bundle Dependencies (Do NOT build AppImage yet)
# =========================================================
echo "🚀 Phase 1: Bundling Python & Dependencies..."
linuxdeploy \
  --appdir AppDir \
  --plugin python \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop

# =========================================================
# PHASE 2: Hijack the Launch Script (The Critical Fix)
# =========================================================
echo "🔧 Phase 2: Forcing use of local start script..."
# Remove the generic AppRun created by the python plugin
rm -f AppDir/AppRun
# Link AppRun to OUR script (which has the correct paths and shebang)
ln -s usr/bin/flipstack AppDir/AppRun

# =========================================================
# PHASE 3: Pack the AppImage
# =========================================================
echo "📦 Phase 3: Generating AppImage..."
# We run linuxdeploy again WITHOUT the python plugin to pack the result
linuxdeploy \
  --appdir AppDir \
  --output appimage

echo "🎉 Success! You can find your AppImage in this folder."
