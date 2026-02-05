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

# CRITICAL FIX: Bundle GTK 4.0 Stylesheets (Fixes Square Buttons)
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

# Schemas (Retaining schema copy for theme logic)
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

# 2. GTK RESOURCE PATHS (Fixes Square Buttons)
# Forces GTK to look inside AppDir for its standard css/assets
export GTK_DATA_PREFIX="$APPDIR/usr"
export GTK_PATH="$APPDIR/usr/lib/gtk-4.0"

# 3. UI SETTINGS
export ADW_DISABLE_PORTAL=1
export GSETTINGS_BACKEND=memory
export GTK_IM_MODULE=gtk-im-context-simple

# 4. RUNTIME CACHE (Avatars)
export GDK_PIXBUF_MODULEDIR="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"
export GDK_PIXBUF_MODULE_FILE="/tmp/flipstack_loaders_$$.cache"
"$APPDIR/usr/bin/gdk-pixbuf-query-loaders" "$GDK_PIXBUF_MODULEDIR"/*.so > "$GDK_PIXBUF_MODULE_FILE" 2>/dev/null

# 5. LAUNCH
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
