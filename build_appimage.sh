#!/bin/bash
set -e

# 1. SETUP PATHS
REPO_ROOT=$(pwd)
mkdir -p "$REPO_ROOT/bin"
export PATH="$REPO_ROOT/bin:$PATH"

# 2. CLEANUP
rm -rf AppDir FlipStack*.AppImage

# 3. DOWNLOAD TOOLS (NOW INCLUDING APPIMAGETOOL)
echo "⬇️  Downloading Build Tools..."
wget -q https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
wget -q https://github.com/niess/linuxdeploy-plugin-python/releases/download/continuous/linuxdeploy-plugin-python-x86_64.AppImage
# NEW: Download the packer explicitly
wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage

chmod +x linuxdeploy*.AppImage appimagetool*.AppImage

# 4. INSTALL APP
echo "📦 Installing dependencies..."
mkdir -p AppDir/usr/lib/python3.12/site-packages
export PYTHONPATH="$REPO_ROOT/AppDir/usr/lib/python3.12/site-packages:$PYTHONPATH"
python3 -m pip install . --target="$REPO_ROOT/AppDir/usr/lib/python3.12/site-packages" --upgrade

# 5. ASSETS
echo "🎨 Setting up assets..."
mkdir -p AppDir/usr/share/applications
mkdir -p AppDir/usr/share/icons/hicolor/scalable/apps
cp io.github.dagaza.FlipStack.desktop AppDir/usr/share/applications/
cp assets/icons/io.github.dagaza.FlipStack.svg AppDir/usr/share/icons/hicolor/scalable/apps/

export VERSION="1.0.0"

# =========================================================
# PHASE 1: PRE-BUNDLING (Manual)
# =========================================================
echo "🐍 Manual Bundling..."
mkdir -p AppDir/usr/bin
cp $(which python3) AppDir/usr/bin/python3
mkdir -p AppDir/usr/lib
cp -r /usr/lib/python3.12 AppDir/usr/lib/

DYNLOAD_DIR=$(python3 -c "import _csv; import os; print(os.path.dirname(_csv.__file__))")
if [ -d "$DYNLOAD_DIR" ]; then cp -r "$DYNLOAD_DIR" AppDir/usr/lib/python3.12/; else cp -r /usr/lib/python3.12/lib-dynload AppDir/usr/lib/python3.12/; fi

mkdir -p AppDir/usr/lib/girepository-1.0
if [ -d "/usr/lib/x86_64-linux-gnu/girepository-1.0" ]; then cp -r /usr/lib/x86_64-linux-gnu/girepository-1.0/* AppDir/usr/lib/girepository-1.0/; fi

# --- FIX 1: ICONS (STATIC) ---
echo "🖼️  Bundling Image Loaders..."
LOADER_DIR=AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders
mkdir -p $LOADER_DIR
cp /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders/*.so $LOADER_DIR/

QUERY_TOOL=$(find /usr -name gdk-pixbuf-query-loaders* -type f -executable 2>/dev/null | head -n 1)
"$QUERY_TOOL" $LOADER_DIR/*.so > AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache
sed -i -E 's|"/[^"]*/([^/]+\.so)"|"\1"|g' AppDir/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache

# --- FIX 2: THEME RESOURCES ---
echo "🎨 Bundling Theme Resources..."
mkdir -p AppDir/usr/share/icons
cp -r /usr/share/icons/Adwaita AppDir/usr/share/icons/
cp -r /usr/share/icons/hicolor AppDir/usr/share/icons/

echo "🎨 Bundling GTK 4 Resources..."
mkdir -p AppDir/usr/share/gtk-4.0
if [ -d "/usr/share/gtk-4.0" ]; then cp -r /usr/share/gtk-4.0/* AppDir/usr/share/gtk-4.0/; fi

mkdir -p AppDir/usr/etc/gtk-4.0
cat > AppDir/usr/etc/gtk-4.0/settings.ini << 'EOF'
[Settings]
gtk-theme-name=Adwaita
gtk-icon-theme-name=Adwaita
gtk-xft-antialias=1
EOF

# =========================================================
# PHASE 2: LINUXDEPLOY (Fill the AppDir)
# =========================================================
echo "⚙️  Running LinuxDeploy (Preparation Only)..."

# Helper to find libs
find_lib() { find /usr/lib/x86_64-linux-gnu -name "$1" | head -n 1; }

LIBS=(
  $(find_lib "libadwaita-1.so.0")
  $(find_lib "librsvg-2.so.2")
  $(find_lib "libpixbufloader-svg.so")
  $(find_lib "libxml2.so.2")
  $(find_lib "libcairo.so.2")
  $(find_lib "libpango-1.0.so.0")
  $(find_lib "libpangocairo-1.0.so.0")
  $(find_lib "libharfbuzz.so.0")
  $(find_lib "libthai.so.0")
)
LIB_ARGS=""
for lib in "${LIBS[@]}"; do LIB_ARGS="$LIB_ARGS --library $lib"; done

# RUN WITHOUT OUTPUT FLAG (Just populates the folder)
./linuxdeploy-x86_64.AppImage \
  --appdir AppDir \
  --plugin gtk \
  --executable AppDir/usr/bin/python3 \
  $LIB_ARGS \
  --icon-file assets/icons/io.github.dagaza.FlipStack.svg \
  --desktop-file io.github.dagaza.FlipStack.desktop

# =========================================================
# PHASE 3: INJECTION (The "Fortress" Fix)
# =========================================================
echo "💉 Injecting Schemas and AppRun..."

# 1. INSTALL SCHEMAS
mkdir -p AppDir/usr/share/glib-2.0/schemas
cp /usr/share/glib-2.0/schemas/*.xml AppDir/usr/share/glib-2.0/schemas/
SCHEMA_SRC=$(find /usr/share/glib-2.0/schemas -name "*org.gnome.desktop.interface.gschema.xml" | head -n 1)

if [ -n "$SCHEMA_SRC" ]; then
    cp "$SCHEMA_SRC" AppDir/usr/share/glib-2.0/schemas/
    echo "✅ Copied org.gnome.desktop.interface schema"
else
    echo "❌ CRITICAL ERROR: Could not find org.gnome.desktop.interface schema!"
    exit 1
fi

# 2. APPLY OVERRIDE
cat > AppDir/usr/share/glib-2.0/schemas/99_flipstack.gschema.override << 'EOF'
[org.gnome.desktop.interface]
color-scheme='prefer-dark'
gtk-theme='Adwaita'
EOF

# 3. COMPILE SCHEMAS (Inside AppDir)
glib-compile-schemas AppDir/usr/share/glib-2.0/schemas

# 4. OVERWRITE APPRUN (With Diagnostics)
rm -f AppDir/AppRun
cat > AppDir/AppRun << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "${0}")")"

# ENV SETUP
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

export PYTHONUNBUFFERED=1
export GSETTINGS_BACKEND=keyfile
export XDG_CONFIG_HOME="/tmp/flipstack_appimage_config"
mkdir -p "$XDG_CONFIG_HOME/glib-2.0/settings"

export ADW_DISABLE_PORTAL=1
export GTK_IM_MODULE=gtk-im-context-simple

# AVATARS
export GDK_PIXBUF_MODULEDIR="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders"
export GDK_PIXBUF_MODULE_FILE="$APPDIR/usr/lib/gdk-pixbuf-2.0/2.10.0/loaders.cache"

# PROBE
echo "🔍 Checking Schema..."
if [ -f "$GSETTINGS_SCHEMA_DIR/gschemas.compiled" ]; then
    echo "✅ Schema file exists."
    # Check if our key exists
    if gsettings list-keys org.gnome.desktop.interface | grep -q color-scheme; then
       echo "✅ 'color-scheme' key found."
    else
       echo "❌ Schema file exists, but 'color-scheme' key is MISSING."
    fi
else
    echo "❌ CRITICAL: gschemas.compiled is MISSING."
fi

exec "$APPDIR/usr/bin/python3" -m main "$@"
EOF
chmod +x AppDir/AppRun

# =========================================================
# PHASE 4: PACKING (Manual)
# =========================================================
echo "📦 Phase 4: Packing AppImage..."

# We must use appimagetool explicitly now
./appimagetool-x86_64.AppImage AppDir FlipStack-x86_64.AppImage

echo "🎉 Success! Created FlipStack-x86_64.AppImage"
