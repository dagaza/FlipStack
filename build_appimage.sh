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

# 6. PATCH DESKTOP FILE
sed -i 's|^Exec=.*|Exec=flipstack|' AppDir/usr/share/applications/io.github.dagaza.FlipStack.desktop

export VERSION="1.0.0"
export LINUXDEPLOY_OUTPUT_VERSION="$VERSION"

# =========================================================
# PHASE 1: Bundle Dependencies
# =========================================================
echo "🚀 Phase 1: Bundling Python & Dependencies..."
linuxdeploy \
  --appdir AppDir \
  --plugin python \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop

# =========================================================
# PHASE 2: MANUAL OVERRIDE (Smart Search Version)
# =========================================================
echo "🔧 Phase 2: Writing smart AppRun script..."

# Delete the auto-generated launcher
rm -f AppDir/AppRun

# Create a smart launcher that hunts for the site-packages
cat > AppDir/AppRun << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "${0}")")"

# 1. FIND SITE-PACKAGES (Handles py3.8, 3.10, 3.11, etc.)
# We look for the first directory named 'site-packages' inside the AppDir
SITE_PACKAGES=$(find "$APPDIR" -name "site-packages" -type d | head -n 1)

if [ -z "$SITE_PACKAGES" ]; then
  # Fallback: check for dist-packages
  SITE_PACKAGES=$(find "$APPDIR" -name "dist-packages" -type d | head -n 1)
fi

echo "🔍 Debug: Found packages at $SITE_PACKAGES" 1>&2

# 2. SET ENVIRONMENT VARIABLES
export PYTHONPATH="$SITE_PACKAGES:$PYTHONPATH"
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0:$APPDIR/usr/local/lib/girepository-1.0:$GI_TYPELIB_PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

# 3. FIND PYTHON EXECUTABLE
# Look for 'python3' or similar executable files
PYTHON_BIN=$(find "$APPDIR" -name "python3*" -type f -executable | grep -v "config" | head -n 1)

echo "🔍 Debug: Using Python at $PYTHON_BIN" 1>&2

# 4. LAUNCH
exec "$PYTHON_BIN" -m main "$@"
EOF

# Make it executable
chmod +x AppDir/AppRun

# =========================================================
# PHASE 3: Pack the AppImage
# =========================================================
echo "📦 Phase 3: Generating AppImage..."
linuxdeploy \
  --appdir AppDir \
  --output appimage

echo "🎉 Success! You can find your AppImage in this folder."
