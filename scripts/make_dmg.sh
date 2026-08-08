#!/bin/bash
# Wrap dist/IDPhotoStudio.app into a distributable DMG with an Applications
# symlink, so installing is a drag-and-drop.
set -euo pipefail

cd "$(dirname "$0")/.."

RAW_VERSION="${1:-0.0.0}"
VERSION="${RAW_VERSION#v}"
APP="dist/IDPhotoStudio.app"
DMG="dist/IDPhotoStudio-${VERSION}-macOS-arm64.dmg"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

if [ ! -d "$APP" ]; then
    echo "error: $APP not found; run PyInstaller first" >&2
    exit 1
fi

# Ad-hoc sign so macOS reports a broken signature instead of silently killing
# the process; unsigned PyInstaller bundles can fail to launch on arm64.
codesign --force --deep --sign - "$APP"

cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

rm -f "$DMG"
hdiutil create \
    -volname "IDPhotoStudio ${VERSION}" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "$DMG"

echo "built $DMG"
