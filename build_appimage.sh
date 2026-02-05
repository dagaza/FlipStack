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

# --- FIX 1: AVATARS (TOOLS) ---
echo "🖼️  Bundling Image Loader Tools..."
LOADER_DIR=AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders
mkdir -p $LOADER_DIR
cp /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders/*.so $LOADER_DIR/
QUERY_TOOL=$(find /usr -name gdk-pixbuf-query-loaders* -type f -executable 2>/dev/null | head -n 1)
cp "$QUERY_TOOL" AppDir/usr/bin/gdk-pixbuf-query-loaders

# --- FIX 2: THEME RESOURCES ---
echo "🎨 Bundling Theme Resources..."
mkdir -p AppDir/usr/share/icons
cp -r /usr/share/icons/Adwaita AppDir/usr/share/icons/
cp -r /usr/share/icons/hicolor AppDir/usr/share/icons/

echo "🎨 Bundling GTK 4 Resources..."
mkdir -p AppDir/usr/share/gtk-4.0
if [ -d "/usr/share/gtk-4.0" ]; then
    cp -r /usr/share/gtk-4.0/* AppDir/usr/share/gtk-4.0/
fi

# Settings File
mkdir -p AppDir/usr/etc/gtk-4.0
cat > AppDir/usr/etc/gtk-4.0/settings.ini << 'EOF'
[Settings]
gtk-theme-name=Adwaita
gtk-icon-theme-name=Adwaita
gtk-xft-antialias=1
EOF

# Schemas
echo "⚙️  Bundling Desktop Schemas..."
mkdir -p AppDir/usr/share/glib-2.0/schemas
cp /usr/share/glib-2.0/schemas/*.xml AppDir/usr/share/glib-2.0/schemas/
SCHEMA_SRC=$(find /usr/share/glib-2.0/schemas -name "*org.gnome.desktop.interface.gschema.xml" | head -n 1)
if [ -n "$SCHEMA_SRC" ]; then cp "$SCHEMA_SRC" AppDir/usr/share/glib-2.0/schemas/; fi
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
export GTK_DATA_PREFIX="$APPDIR/usr"
export GTK_PATH="$APPDIR/usr/lib/gtk-4.0"

# 2. DEBUG MODE (The Loud Fix)
export G_MESSAGES_DEBUG=all 
export GTK_DEBUG=0

# 3. SETTINGS BACKEND (KEYFILE)
export GSETTINGS_BACKEND=keyfile
export XDG_CONFIG_HOME="/tmp/flipstack_config_$$"
mkdir -p "$XDG_CONFIG_HOME/glib-2.0/settings"

# 4. PORTAL & INPUT
export ADW_DISABLE_PORTAL=1
export GTK_IM_MODULE=gtk-im-context-simple

# 5. RUNTIME CACHE
export GDK_PIXBUF_MODULEDIR="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"
export GDK_PIXBUF_MODULE_FILE="/tmp/flipstack_loaders_$$.cache"
"$APPDIR/usr/bin/gdk-pixbuf-query-loaders" "$GDK_PIXBUF_MODULEDIR"/*.so > "$GDK_PIXBUF_MODULE_FILE" 2>/dev/null

# --- DIAGNOSTICS START ---
echo "--- DEBUG PROBE ---"
echo "Checking for 'color-scheme' key in schemas..."
if grep -q "color-scheme" "$GSETTINGS_SCHEMA_DIR/gschemas.compiled"; then
    echo "✅ 'color-scheme' key found in compiled schemas."
else
    echo "❌ CRITICAL: 'color-scheme' key MISSING in compiled schemas."
fi
echo "--- END PROBE ---"
# --- DIAGNOSTICS END ---

# 6. LAUNCH
exec "$APPDIR/usr/bin/python3" -m main "$@"
EOF

chmod +x AppDir/AppRun

# =========================================================
# PHASE 3: PACK
# =========================================================
echo "📦 Phase 3: Packing..."

export DEPLOY_GTK_VERSION=4
# Helper to find libs
find_lib() { find /usr/lib/x86_64-linux-gnu -name "$1" | head -n 1; }

LIBADWAITA=$(find_lib "libadwaita-1.so.0")
LIBRSVG=$(find_lib "librsvg-2.so.2")
SVG_LOADER=$(find_lib "libpixbufloader-svg.so")
LIBXML2=$(find_lib "libxml2.so.2")
LIBCAIRO=$(find_lib "libcairo.so.2")

# SVG TEXT RENDERING DEPENDENCIES (New additions)
LIBPANGO=$(find_lib "libpango-1.0.so.0")
LIBPANGOCAIRO=$(find_lib "libpangocairo-1.0.so.0")
LIBHARFBUZZ=$(find_lib "libharfbuzz.so.0")
LIBTHAI=$(find_lib "libthai.so.0")

linuxdeploy \
  --appdir AppDir \
  --plugin gtk \
  --executable AppDir/usr/bin/python3 \
  --library "$LIBADWAITA" \
  --library "$LIBRSVG" \
  --library "$SVG_LOADER" \
  --library "$LIBXML2" \
  --library "$LIBCAIRO" \
  --library "$LIBPANGO" \
  --library "$LIBPANGOCAIRO" \
  --library "$LIBHARFBUZZ" \
  --library "$LIBTHAI" \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop \
  --output appimage
