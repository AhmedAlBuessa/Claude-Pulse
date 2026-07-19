#!/bin/bash
# Build Claude Pulse Bar into a native .app bundle installed in ~/Applications.
# Requires Xcode / command-line tools (swiftc). macOS only.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP="${1:-$HOME/Applications/ClaudePulseBar.app}"
MACOS="$APP/Contents/MacOS"

echo "Building $APP"
rm -rf "$APP"
mkdir -p "$MACOS" "$APP/Contents/Resources"

swiftc -O -o "$MACOS/ClaudePulseBar" "$SRC_DIR/main.swift" -framework Cocoa
cp "$SRC_DIR/claude-logo.png" "$APP/Contents/Resources/claude-logo.png"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Claude Pulse Bar</string>
    <key>CFBundleDisplayName</key><string>Claude Pulse Bar</string>
    <key>CFBundleIdentifier</key><string>com.claudepulse.menubar</string>
    <key>CFBundleExecutable</key><string>ClaudePulseBar</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleVersion</key><string>0.2.0</string>
    <key>CFBundleShortVersionString</key><string>0.2.0</string>
    <key>LSUIElement</key><true/>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST

# Ad-hoc code signature so macOS will launch it.
codesign --force --sign - "$APP" >/dev/null 2>&1 || true

echo "Done: $APP"
echo "Launch it:  open \"$APP\""
