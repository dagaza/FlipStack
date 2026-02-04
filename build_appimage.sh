#!/bin/bash
set -e  # Stop on error

# 1. SETUP PATHS
REPO_ROOT=$(pwd)
mkdir -p "$REPO_ROOT/bin"
if [ -f "$REPO_ROOT/linuxdeploy-root/AppRun" ]; then
    ln -sf "$REPO_ROOT/linuxdeploy-root/AppRun" "$REPO_ROOT/bin/linuxdeploy"
fi

# --- DOWNLOAD GTK PLUGIN ---
if [ ! -f "$REPO_ROOT/bin/linuxdeploy-plugin-gtk.sh" ]; then
    echo "⬇️ Downloading GTK Plugin..."
    wget -q https://raw.githubusercontent.com/linuxdeploy/linuxdeploy-plugin-gtk/master/linuxdeploy-plugin-gtk.sh -O "$REPO_ROOT/bin/linuxdeploy-plugin-gtk.sh"
    chmod +x "$REPO_ROOT/bin/linuxdeploy-plugin-gtk.sh"
fi
export PATH="$REPO_ROOT/bin:$PATH"
echo "✅ Tools setup in $REPO_ROOT/bin"

# 2. CLEANUP
rm -rf AppDir FlipStack*.AppImage

# 3. INSTALL APP & DEPENDENCIES
echo "📦 Installing dependencies to AppDir..."
mkdir -p AppDir/usr/lib/python3.10/site-packages
export PYTHONPATH="$REPO_ROOT/AppDir/usr/lib/python3.10/site-packages:$PYTHONPATH"

python3 -m pip install . --target="$REPO_ROOT/AppDir/usr/lib/python3.10/site-packages" --upgrade

# 4. ASSETS & DESKTOP INTEGRATION
echo "🎨 Setting up assets..."
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp io.github.dagaza.FlipStack.desktop AppDir/usr/share/applications/
cp assets/icons/io.github.dagaza.FlipStack.svg AppDir/usr/share/icons/hicolor/scalable/apps/
sed -i 's|^Exec=.*|Exec=AppRun|' AppDir/usr/share/applications/io.github.dagaza.FlipStack.desktop

export VERSION="1.0.0"

# =========================================================
# PHASE 1.5: MANUAL PYTHON BUNDLING
# =========================================================
echo "🐍 Manual Bundling: Copying System Python 3.10..."

# A. Copy Executable
mkdir -p AppDir/usr/bin
cp $(which python3) AppDir/usr/bin/python3

# B. Copy Standard Lib
mkdir -p AppDir/usr/lib
cp -r /usr/lib/python3.10 AppDir/usr/lib/

# C. Copy Binary Extensions (lib-dynload)
DYNLOAD_DIR=$(python3 -c "import _csv; import os; print(os.path.dirname(_csv.__file__))")
if [ -d "$DYNLOAD_DIR" ]; then
    cp -r "$DYNLOAD_DIR" AppDir/usr/lib/python3.10/
else
    cp -r /usr/lib/python3.10/lib-dynload AppDir/usr/lib/python3.10/
fi

# D. Copy GObject TypeLibs
mkdir -p AppDir/usr/lib/girepository-1.0
if [ -d "/usr/lib/x86_64-linux-gnu/girepository-1.0" ]; then
    cp -r /usr/lib/x86_64-linux-gnu/girepository-1.0/* AppDir/usr/lib/girepository-1.0/
fi

# =========================================================
# PHASE 2: MANUAL APPRUN (Strict Environment)
# =========================================================
echo "🔧 Writing AppRun script..."
rm -f AppDir/AppRun

cat > AppDir/AppRun << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "${0}")")"

# 1. SETUP PYTHON ENVIRONMENT
export PATH="$APPDIR/usr/bin:$PATH"
export PYTHONHOME="$APPDIR/usr"
export PYTHONPATH="$APPDIR/usr/lib/python3.10:$APPDIR/usr/lib/python3.10/lib-dynload:$APPDIR/usr/lib/python3.10/site-packages:$PYTHONPATH"

# 2. SETUP GTK/GLIB ENVIRONMENT
export XDG_DATA_DIRS="$APPDIR/usr/share:$XDG_DATA_DIRS"
export GSETTINGS_SCHEMA_DIR="$APPDIR/usr/share/glib-2.0/schemas:$GSETTINGS_SCHEMA_DIR"
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0:$GI_TYPELIB_PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

# --- THE FIX IS HERE ---
# Prevent loading incompatible system GIO modules
export GIO_MODULE_DIR="$APPDIR/usr/lib/gio/modules"
# Unset any user overrides that might point to system paths
unset GIO_EXTRA_MODULES
# -----------------------

# 3. DEBUG INFO
echo "🔍 Debug: Launching..."
echo "Using Python: $APPDIR/usr/bin/python3"

# 4. RUN APP
exec "$APPDIR/usr/bin/python3" -m main "$@"
EOF

chmod +x AppDir/AppRun

# =========================================================
# PHASE 3: DEPLOY & PACK
# =========================================================
echo "📦 Phase 3: Packing AppImage with GTK Plugin..."

export DEPLOY_GTK_VERSION=4

# Locate LibAdwaita
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
