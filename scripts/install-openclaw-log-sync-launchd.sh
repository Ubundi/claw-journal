#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/openclaw-sync-tmp-logs.sh"

if [[ ! -x "$SYNC_SCRIPT" ]]; then
  chmod +x "$SYNC_SCRIPT"
fi

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/io.ubundi.openclaw-log-sync.plist"
mkdir -p "$PLIST_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>io.ubundi.openclaw-log-sync</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>$SYNC_SCRIPT</string>
    </array>

    <key>StartInterval</key>
    <integer>120</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$HOME/.openclaw/logs/log-sync.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.openclaw/logs/log-sync.stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
      <key>OPENCLAW_TMP_LOG_DIR</key>
      <string>/tmp/openclaw</string>
      <key>OPENCLAW_PERSISTENT_LOG_DIR</key>
      <string>$HOME/.openclaw/logs/history</string>
      <key>OPENCLAW_TMP_LOG_PATTERN</key>
      <string>openclaw-*.log</string>
    </dict>
  </dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH"
launchctl start io.ubundi.openclaw-log-sync || true

echo "Installed launchd agent: $PLIST_PATH"
echo "Sync script: $SYNC_SCRIPT"
echo "Persistent logs: $HOME/.openclaw/logs/history"
