#!/bin/bash
set -e  # Stop on error

# 1. SETUP PATHS
REPO_ROOT=$(pwd)
mkdir -p "$REPO_ROOT/bin"
if [ -f "$REPO_ROOT/linuxdeploy-root/AppRun" ]; then
    ln -sf "$REPO_ROOT/linuxdeploy-root/AppRun" "$REPO_ROOT/bin/linuxdeploy"
fi

export PATH="$REPO_ROOT/bin:$PATH"
echo "✅ Tools setup in $REPO_ROOT/bin"

# 2. CLEANUP
rm -rf AppDir FlipStack*.AppImage

# 3. INSTALL APP & DEPENDENCIES
echo "📦 Installing dependencies to AppDir..."
# TARGET: PYTHON 3.12 (Standard on Ubuntu 24.04)
mkdir -p AppDir/usr/lib/python3.12/site-packages
export PYTHONPATH="$REPO_ROOT/AppDir/usr/lib/python3.12/site-packages:$PYTHONPATH"

python3 -m pip install . --target="$REPO_ROOT/AppDir/usr/lib/python3.12/site-packages" --upgrade

# 4. ASSETS & DESKTOP INTEGRATION
echo "🎨 Setting up assets..."
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp io.github.dagaza.FlipStack.desktop AppDir/usr/share/applications/
cp assets/icons/io.github.dagaza.FlipStack.svg AppDir/usr/share/icons/hicolor/scalable/apps/
sed -i 's|^Exec=.*|Exec=AppRun|' AppDir/usr/share/applications/io.github.dagaza.FlipStack.desktop

export VERSION="1.0.0"

# =========================================================
# PHASE 1.5: MANUAL PYTHON BUNDLING (Python 3.12 Edition)
# =========================================================
echo "🐍 Manual Bundling: Copying System Python 3.12..."

# A. Copy Executable
mkdir -p AppDir/usr/bin
cp $(which python3) AppDir/usr/bin/python3

# B. Copy Standard Lib
mkdir -p AppDir/usr/lib
cp -r /usr/lib/python3.12 AppDir/usr/lib/

# C. Copy Binary Extensions (lib-dynload)
# On Python 3.12, verifying location is still best practice
DYNLOAD_DIR=$(python3 -c "import _csv; import os; print(os.path.dirname(_csv.__file__))")
if [ -d "$DYNLOAD_DIR" ]; then
    cp -r "$DYNLOAD_DIR" AppDir/usr/lib/python3.12/
else
    cp -r /usr/lib/python3.12/lib-dynload AppDir/usr/lib/python3.12/
fi

# D. Copy GObject TypeLibs
mkdir -p AppDir/usr/lib/girepository-1.0
if [ -d "/usr/lib/x86_64-linux-gnu/girepository-1.0" ]; then
    cp -r /usr/lib/x86_64-linux-gnu/girepository-1.0/* AppDir/usr/lib/girepository-1.0/
fi

# =========================================================
# PHASE 2: MANUAL APPRUN
# =========================================================
echo "🔧 Writing AppRun script..."
rm -f AppDir/AppRun

cat > AppDir/AppRun << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "${0}")")"

# 1. SETUP PYTHON ENVIRONMENT
export PATH="$APPDIR/usr/bin:$PATH"
export PYTHONHOME="$APPDIR/usr"
# Note 3.12 paths here
export PYTHONPATH="$APPDIR/usr/lib/python3.12:$APPDIR/usr/lib/python3.12/lib-dynload:$APPDIR/usr/lib/python3.12/site-packages:$PYTHONPATH"

# 2. SETUP GTK/GLIB ENVIRONMENT
export XDG_DATA_DIRS="$APPDIR/usr/share:$XDG_DATA_DIRS"
export GSETTINGS_SCHEMA_DIR="$APPDIR/usr/share/glib-2.0/schemas:$GSETTINGS_SCHEMA_DIR"
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0:$GI_TYPELIB_PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

# 3. ISOLATE MODULES
# Prevent loading incompatible system GIO modules
export GIO_MODULE_DIR="$APPDIR/usr/lib/gio/modules"
unset GIO_EXTRA_MODULES

# 4. DEBUG INFO
echo "🔍 Debug: Launching..."
echo "Using Python: $APPDIR/usr/bin/python3"

# 5. RUN APP
exec "$APPDIR/usr/bin/python3" -m main "$@"
EOF

chmod +x AppDir/AppRun

# =========================================================
# PHASE 3: DEPLOY & PACK
# =========================================================
echo "📦 Phase 3: Packing AppImage with GTK Plugin..."

export DEPLOY_GTK_VERSION=4

# Locate LibAdwaita (Updated search path if necessary)
LIBADWAITA_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libadwaita-1.so.0" | head -n 1)
echo "🔍 Found LibAdwaita at: $LIBADWAITA_PATH"

linuxdeploy \
  --appdir AppDir \
  --plugin gtk \
  --executable AppDir/usr/bin/python3 \
  --library "$LIBADWAITA_PATH" \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop \
  --output appimage

echo "🎉 Success! You can find your AppImage in this folder."
