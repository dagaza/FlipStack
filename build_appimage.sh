#!/bin/bash
set -e  # Stop instantly if any command fails

# 1. SETUP PATHS
REPO_ROOT=$(pwd)
mkdir -p "$REPO_ROOT/bin"
ln -sf "$REPO_ROOT/linuxdeploy-root/AppRun" "$REPO_ROOT/bin/linuxdeploy"
ln -sf "$REPO_ROOT/linuxdeploy-plugin-python-root/AppRun" "$REPO_ROOT/bin/linuxdeploy-plugin-python"
export PATH="$REPO_ROOT/bin:$PATH"

echo "✅ Tools setup in $REPO_ROOT/bin"

# 2. CLEANUP
rm -rf AppDir FlipStack*.AppImage

# 3. INSTALL APP
echo "📦 Installing dependencies..."
python3 -m pip install . --prefix="$REPO_ROOT/AppDir/usr" --break-system-packages

# 4. MANUALLY COPY ASSETS
SITE_PACKAGES=$(find AppDir -type d \( -name "site-packages" -o -name "dist-packages" \) | head -n 1)

if [ -z "$SITE_PACKAGES" ]; then
    echo "❌ ERROR: Could not find site-packages in AppDir."
    exit 1
fi

echo "📂 Found packages at: $SITE_PACKAGES"
cp -r assets "$SITE_PACKAGES/"

# 5. DESKTOP INTEGRATION
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp io.github.dagaza.FlipStack.desktop AppDir/usr/share/applications/
cp assets/icons/io.github.dagaza.FlipStack.svg AppDir/usr/share/icons/hicolor/scalable/apps/

# 6. FIX EXECUTABLE LOCATION (The Fix!)
# Find the 'flipstack' binary wherever pip put it (likely usr/local/bin)
BINARY=$(find AppDir -name "flipstack" -type f | head -n 1)

if [ -z "$BINARY" ]; then
    echo "❌ ERROR: Could not find 'flipstack' executable."
    exit 1
fi

# Move it to usr/bin where linuxdeploy expects it
mkdir -p AppDir/usr/bin
if [ "$BINARY" != "AppDir/usr/bin/flipstack" ]; then
    echo "🚚 Moving executable from $BINARY to AppDir/usr/bin/"
    mv "$BINARY" AppDir/usr/bin/
fi

# 7. PATCH DESKTOP FILE
# Ensure the Exec line is just 'Exec=flipstack', not an absolute path like '/app/bin/flipstack'
sed -i 's|^Exec=.*|Exec=flipstack|' AppDir/usr/share/applications/io.github.dagaza.FlipStack.desktop

# 8. BUILD APPIMAGE
export VERSION="1.0.0"
export LINUXDEPLOY_OUTPUT_VERSION="$VERSION"

echo "🚀 Building AppImage..."
linuxdeploy \
  --appdir AppDir \
  --plugin python \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop \
  --output appimage

echo "🎉 Success! You can find your AppImage in this folder."
