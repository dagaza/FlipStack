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
# PHASE 1.5: MANUAL BUNDLING
# =========================================================
echo "🐍 Manual Bundling: Python & Core..."

# A. Copy Python 3.12
mkdir -p AppDir/usr/bin
cp $(which python3) AppDir/usr/bin/python3
mkdir -p AppDir/usr/lib
cp -r /usr/lib/python3.12 AppDir/usr/lib/

# B. Copy Binary Extensions
DYNLOAD_DIR=$(python3 -c "import _csv; import os; print(os.path.dirname(_csv.__file__))")
if [ -d "$DYNLOAD_DIR" ]; then
    cp -r "$DYNLOAD_DIR" AppDir/usr/lib/python3.12/
else
    cp -r /usr/lib/python3.12/lib-dynload AppDir/usr/lib/python3.12/
fi

# C. Copy GObject TypeLibs
mkdir -p AppDir/usr/lib/girepository-1.0
if [ -d "/usr/lib/x86_64-linux-gnu/girepository-1.0" ]; then
    cp -r /usr/lib/x86_64-linux-gnu/girepository-1.0/* AppDir/usr/lib/girepository-1.0/
fi

# --- FIX 1: AVATARS (RELATIVE PATHS) ---
echo "🖼️  Bundling Image Loaders..."
mkdir -p AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders
cp /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders/*.so AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders/

QUERY_LOADERS=$(find /usr -name gdk-pixbuf-query-loaders* -type f -executable 2>/dev/null | head -n 1)
if [ -z "$QUERY_LOADERS" ]; then
    echo "❌ Error: Could not find gdk-pixbuf-query-loaders tool."
    exit 1
fi

# Generate Cache
"$QUERY_LOADERS" AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders/*.so > AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache

# CHECKSUM FIX: Strip absolute paths so GDK looks in the AppRun defined folder
sed -i -E 's|"/[^"]*/([^/]+\.so)"|"\1"|g' AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache

# --- FIX 2: UI THEME (CONFIG & SCHEMAS) ---
echo "🎨 Bundling Theme Resources..."
mkdir -p AppDir/usr/share/icons
cp -r /usr/share/icons/Adwaita AppDir/usr/share/icons/
cp -r /usr/share/icons/hicolor AppDir/usr/share/icons/

# Create Settings File (Clean version)
mkdir -p AppDir/usr/etc/gtk-4.0
cat > AppDir/usr/etc/gtk-4.0/settings.ini << 'EOF'
[Settings]
gtk-theme-name=Adwaita
gtk-icon-theme-name=Adwaita
gtk-xft-antialias=1
gtk-xft-hinting=1
gtk-xft-hintstyle=hintfull
EOF

# Compile Schemas
mkdir -p AppDir/usr/share/glib-2.0/schemas
cp /usr/share/glib-2.0/schemas/*.xml AppDir/usr/share/glib-2.0/schemas/
glib-compile-schemas AppDir/usr/share/glib-2.0/schemas

# =========================================================
# PHASE 2: MANUAL APPRUN
# =========================================================
echo "🔧 Writing AppRun script..."
rm -f AppDir/AppRun

cat > AppDir/AppRun << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "${0}")")"

# 1. SETUP PYTHON
export PATH="$APPDIR/usr/bin:$PATH"
export PYTHONHOME="$APPDIR/usr"
export PYTHONPATH="$APPDIR/usr/lib/python3.12:$APPDIR/usr/lib/python3.12/lib-dynload:$APPDIR/usr/lib/python3.12/site-packages:$PYTHONPATH"

# 2. SETUP GTK/GLIB
export XDG_DATA_DIRS="$APPDIR/usr/share:$XDG_DATA_DIRS"
export GSETTINGS_SCHEMA_DIR="$APPDIR/usr/share/glib-2.0/schemas:$GSETTINGS_SCHEMA_DIR"
export GI_TYPELIB_PATH="$APPDIR/usr/lib/girepository-1.0:$GI_TYPELIB_PATH"
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

# 3. FIX UI & TOGGLE BUTTON
export XDG_CONFIG_DIRS="$APPDIR/usr/etc:$XDG_CONFIG_DIRS"
export ADW_DISABLE_PORTAL=1
# CRITICAL FIX: Use memory backend so the toggle works without needing host dconf
export GSETTINGS_BACKEND=memory

# 4. FIX AVATARS
export GDK_PIXBUF_MODULE_FILE="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache"
export GDK_PIXBUF_MODULEDIR="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"

# 5. ISOLATE MODULES
export GIO_MODULE_DIR="$APPDIR/usr/lib/gio/modules"
unset GIO_EXTRA_MODULES
unset GTK_IM_MODULE
export GTK_IM_MODULE_FILE=/dev/null

# 6. LAUNCH
exec "$APPDIR/usr/bin/python3" -m main "$@"
EOF

chmod +x AppDir/AppRun

# =========================================================
# PHASE 3: DEPLOY & PACK
# =========================================================
echo "📦 Phase 3: Packing AppImage..."

export DEPLOY_GTK_VERSION=4

# 1. Find Core Libraries
LIBADWAITA_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libadwaita-1.so.0" | head -n 1)
LIBRSVG_PATH=$(find /usr/lib/x86_64-linux-gnu -name "librsvg-2.so.2" | head -n 1)

# 2. Find SVG Loader & Dependencies (THE AVATAR FIX)
SVG_LOADER_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libpixbufloader-svg.so" | head -n 1)
LIBXML2_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libxml2.so.2" | head -n 1)
LIBCAIRO_PATH=$(find /usr/lib/x86_64-linux-gnu -name "libcairo.so.2" | head -n 1)

echo "🔍 Found Dependencies:"
echo "   - Adwaita: $LIBADWAITA_PATH"
echo "   - Rsvg:    $LIBRSVG_PATH"
echo "   - Loader:  $SVG_LOADER_PATH"
echo "   - Xml2:    $LIBXML2_PATH"

# 3. Bundle EVERYTHING
# We explicitly bundle libxml2 and libcairo to ensure the SVG loader doesn't crash
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

echo "🎉 Success! You can find your AppImage in this folder."
