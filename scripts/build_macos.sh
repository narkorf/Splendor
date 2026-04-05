#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="SplendorDesktop"
APP_BUNDLE="$ROOT_DIR/dist/${APP_NAME}.app"
DMG_PATH="$ROOT_DIR/dist/${APP_NAME}-macOS.dmg"
DMG_STAGING_DIR="$ROOT_DIR/build/dmg-staging"
PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

cd "$ROOT_DIR"

export PYINSTALLER_CONFIG_DIR

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --add-data "splendor_app/assets:splendor_app/assets" \
  packaging_launcher.py

INFO_PLIST="$APP_BUNDLE/Contents/Info.plist"
if [[ -f "$INFO_PLIST" ]]; then
  /usr/libexec/PlistBuddy -c "Delete :NSLocalNetworkUsageDescription" "$INFO_PLIST" >/dev/null 2>&1 || true
  /usr/libexec/PlistBuddy -c "Add :NSLocalNetworkUsageDescription string Discover and join Splendor games on your local network." "$INFO_PLIST"
fi

rm -f "$DMG_PATH"
rm -rf "$DMG_STAGING_DIR"
mkdir -p "$DMG_STAGING_DIR"
cp -R "$APP_BUNDLE" "$DMG_STAGING_DIR/"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$DMG_STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "Created macOS build artifacts:"
echo "  App bundle: $APP_BUNDLE"
echo "  DMG: $DMG_PATH"
