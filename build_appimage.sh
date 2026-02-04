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
# PHASE 1.5: MANUAL PYTHON BUNDLING (Improved)
# =========================================================
echo "🐍 Manual Bundling: Copying System Python 3.10..."

# A. Copy the Python Executable
mkdir -p AppDir/usr/bin
cp $(which python3) AppDir/usr/bin/python3

# B. Copy the Standard Library (Pure Python)
mkdir -p AppDir/usr/lib
cp -r /usr/lib/python3.10 AppDir/usr/lib/

# C. FIND AND COPY BINARY EXTENSIONS (The Fix for '_csv')
# We ask Python where '_csv' lives and copy its parent folder (lib-dynload)
DYNLOAD_DIR=$(python3 -c "import _csv; import os; print(os.path.dirname(_csv.__file__))")
echo "🔍 Found lib-dynload at: $DYNLOAD_DIR"

if [ -d "$DYNLOAD_DIR" ]; then
    cp -r "$DYNLOAD_DIR" AppDir/usr/lib/python3.10/
else
    echo "⚠️ Warning: Could not find lib-dynload via Python. Trying standard path..."
    cp -r /usr/lib/python3.10/lib-dynload AppDir/usr/lib/python3.10/
fi

# D. Copy GObject TypeLibs (Required for 'gi')
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

# 1. SETUP ENVIRONMENT
export PATH="$APPDIR/usr/bin:$PATH"
export PYTHONHOME="$APPDIR/usr"
# We explicitly add lib-dynload to the path just in case
export PYTHONPATH="$APPDIR/usr/lib/python3.10:$APPDIR/usr/lib/python3.10/lib-dynload:$APPDIR/usr/lib/python3.10/site-packages:$PYTHONPATH"

# Setup GObject paths
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0:$GI_TYPELIB_PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

# 2. DEBUG INFO
echo "🔍 Debug: Python Version Check:"
"$APPDIR/usr/bin/python3" --version

# 3. RUN APP
exec "$APPDIR/usr/bin/python3" -m main "$@"
EOF

chmod +x AppDir/AppRun

# =========================================================
# PHASE 3: DEPLOY & PACK
# =========================================================
echo "📦 Phase 3: Packing AppImage..."
linuxdeploy \
  --appdir AppDir \
  --executable AppDir/usr/bin/python3 \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop \
  --output appimage

echo "🎉 Success! You can find your AppImage in this folder."
