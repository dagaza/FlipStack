#!/bin/bash
set -e

# 1. SETUP PATHS
REPO_ROOT=$(pwd)
mkdir -p "$REPO_ROOT/bin"
if [ -f "$REPO_ROOT/linuxdeploy-root/AppRun" ]; then
    ln -sf "$REPO_ROOT/linuxdeploy-root/AppRun" "$REPO_ROOT/bin/linuxdeploy"
fi
export PATH="$REPO_ROOT/bin:$PATH"

# 2. CLEANUP
rm -rf AppDir FlipStack*.AppImage

# 3. INSTALL APP
echo "📦 Installing dependencies..."
mkdir -p AppDir/usr/lib/python3.12/site-packages
export PYTHONPATH="$REPO_ROOT/AppDir/usr/lib/python3.12/site-packages:$PYTHONPATH"
python3 -m pip install . --target="$REPO_ROOT/AppDir/usr/lib/python3.12/site-packages" --upgrade

# 4. ASSETS
echo "🎨 Setting up assets..."
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp io.github.dagaza.FlipStack.desktop AppDir/usr/share/applications/
cp assets/icons/io.github.dagaza.FlipStack.svg AppDir/usr/share/icons/hicolor/scalable/apps/
sed -i 's|^Exec=.*|Exec=AppRun|' AppDir/usr/share/applications/io.github.dagaza.FlipStack.desktop

export VERSION="1.0.0"

# =========================================================
# PHASE 1.5: MANUAL BUNDLING
# =========================================================
echo "🐍 Manual Bundling..."
mkdir -p AppDir/usr/bin
cp $(which python3) AppDir/usr/bin/python3
mkdir -p AppDir/usr/lib
cp -r /usr/lib/python3.12 AppDir/usr/lib/

# Binary Extensions
DYNLOAD_DIR=$(python3 -c "import _csv; import os; print(os.path.dirname(_csv.__file__))")
if [ -d "$DYNLOAD_DIR" ]; then cp -r "$DYNLOAD_DIR" AppDir/usr/lib/python3.12/; else cp -r /usr/lib/python3.12/lib-dynload AppDir/usr/lib/python3.12/; fi

# GObject TypeLibs
mkdir -p AppDir/usr/lib/girepository-1.0
if [ -d "/usr/lib/x86_64-linux-gnu/girepository-1.0" ]; then cp -r /usr/lib/x86_64-linux-gnu/girepository-1.0/* AppDir/usr/lib/girepository-1.0/; fi

# --- FIX 1: AVATARS (STRICT CACHE) ---
echo "🖼️  Bundling Image Loaders..."
LOADER_DIR=AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders
mkdir -p $LOADER_DIR
cp /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders/*.so $LOADER_DIR/

QUERY_LOADERS=$(find /usr -name gdk-pixbuf-query-loaders* -type f -executable 2>/dev/null | head -n 1)
"$QUERY_LOADERS" $LOADER_DIR/*.so > AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache

# CHECKSUM FIX: Strip the prefix so paths are just filenames
sed -i "s|$(pwd)/AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders/||g" AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache

# --- FIX 2: THEME RESOURCES (SCHEMAS) ---
echo "🎨 Bundling Theme Resources..."
mkdir -p AppDir/usr/share/icons
cp -r /usr/share/icons/Adwaita AppDir/usr/share/icons/
cp -r /usr/share/icons/hicolor AppDir/usr/share/icons/

mkdir -p AppDir/usr/etc/gtk-4.0
cat > AppDir/usr/etc/gtk-4.0/settings.ini << 'EOF'
[Settings]
gtk-theme-name=Adwaita
gtk-icon-theme-name=Adwaita
gtk-xft-antialias=1
EOF

# VITAL: Copy Desktop Schemas (Required for Dark Mode/Color Scheme)
mkdir -p AppDir/usr/share/glib-2.0/schemas
# Copy standard system schemas
cp /usr/share/glib-2.0/schemas/*.xml AppDir/usr/share/glib-2.0/schemas/
glib-compile-schemas AppDir/usr/share/glib-2.0/schemas

# =========================================================
# PHASE 2: APPRUN
# =========================================================
echo "🔧 Writing AppRun script..."
rm -f AppDir/AppRun

cat > AppDir/AppRun << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "${0}")")"

# 1. SETUP ENV
export PATH="$APPDIR/usr/bin:$PATH"
export PYTHONHOME="$APPDIR/usr"
export PYTHONPATH="$APPDIR/usr/lib/python3.12:$APPDIR/usr/lib/python3.12/lib-dynload:$APPDIR/usr/lib/python3.12/site-packages:$PYTHONPATH"
export XDG_DATA_DIRS="$APPDIR/usr/share:$XDG_DATA_DIRS"
export GSETTINGS_SCHEMA_DIR="$APPDIR/usr/share/glib-2.0/schemas:$GSETTINGS_SCHEMA_DIR"
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0:$GI_TYPELIB_PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"
export XDG_CONFIG_DIRS="$APPDIR/usr/etc:$XDG_CONFIG_DIRS"

# 2. UI SETTINGS
export ADW_DISABLE_PORTAL=1
export GSETTINGS_BACKEND=memory

# 3. IM MODULE (Fixes ibus warning)
export GTK_IM_MODULE=gtk-im-context-simple

# 4. AVATARS
export GDK_PIXBUF_MODULE_FILE="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache"
export GDK_PIXBUF_MODULEDIR="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"

# --- DIAGNOSTIC PROBE ---
echo "========================================"
echo "🔍 FLIPSTACK DIAGNOSTIC PROBE"
echo "========================================"
echo "📂 AppDir: $APPDIR"

SVG_LOADER="$GDK_PIXBUF_MODULEDIR/libpixbufloader-svg.so"
if [ -f "$SVG_LOADER" ]; then
    echo "✅ SVG Loader found at: $SVG_LOADER"
else
    echo "❌ SVG Loader NOT FOUND"
fi

echo "📂 Content of loaders.cache:"
cat "$GDK_PIXBUF_MODULE_FILE" | grep -A 5 "svg"
echo "========================================"
# --- END PROBE ---

exec "$APPDIR/usr/bin/python3" -m main "$@"
EOF

chmod +x AppDir/AppRun

# =========================================================
# PHASE 3: PACK
# =========================================================
echo "📦 Phase 3: Packing..."

export DEPLOY_GTK_VERSION=4
LIBADWAITA_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libadwaita-1.so.0" | head -n 1)
LIBRSVG_PATH=$(find /usr/lib/x86_64-linux-gnu -name "librsvg-2.so.2" | head -n 1)
SVG_LOADER_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libpixbufloader-svg.so" | head -n 1)
LIBXML2_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libxml2.so.2" | head -n 1)
LIBCAIRO_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libcairo.so.2" | head -n 1)

linuxdeploy \
  --appdir AppDir \
  --plugin gtk \
  --executable AppDir/usr/bin/python3 \
  --library "$LIBADWAITA_PATH" \
  --library "$LIBRSVG_PATH" \
  --library "$SVG_LOADER_PATH" \
  --library "$LIBXML2_PATH" \
  --library "$LIBCAIRO_PATH" \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop \
  --output appimage
