#!/bin/bash
# Weekly unattended run on this Mac (launchd). Usage:
#   scripts/schedule.sh install        # schedule it (default: Mondays 09:00)
#   scripts/schedule.sh status         # is it scheduled, and the last log lines
#   scripts/schedule.sh run-now        # trigger it once right now
#   scripts/schedule.sh uninstall      # remove the schedule
#   scripts/schedule.sh print-plist    # show what would be installed (changes nothing)
# Options (environment): WEEKDAY=1 (0/7=Sunday, 1=Monday ... 6=Saturday)  HOUR=9  MINUTE=0
set -euo pipefail

LABEL="com.jobtracker.weekly"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$PROJECT/.venv/bin/python"
LOGDIR="$PROJECT/appdata/logs"
WEEKDAY="${WEEKDAY:-1}"; HOUR="${HOUR:-9}"; MINUTE="${MINUTE:-0}"
DOMAIN="gui/$(id -u)"

make_plist() {
cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>-m</string><string>jobtracker.headless</string></array>
  <key>WorkingDirectory</key><string>$PROJECT</string>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>$WEEKDAY</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$LOGDIR/headless.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/headless.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin</string></dict>
</dict>
</plist>
PLIST
}

case "${1:-}" in
  print-plist) make_plist ;;
  install)
    [ -x "$PY" ] || { echo "Missing $PY. Run 'uv sync' in $PROJECT first."; exit 1; }
    case "$PROJECT" in
      "$HOME/Downloads"/*|"$HOME/Desktop"/*|"$HOME/Documents"/*)
        if [ "${FORCE:-0}" != "1" ]; then
          echo "This project is inside a macOS-protected folder ($PROJECT)."
          echo "Background jobs are usually blocked from reading Downloads/Desktop/Documents ('Operation not permitted')."
          echo "Move it first, for example:   mv \"$PROJECT\" \"$HOME/Projects/jobtracker\""
          echo "then run:  cd ~/Projects/jobtracker && uv sync && scripts/schedule.sh install"
          echo "(To try anyway: FORCE=1 scripts/schedule.sh install)"
          exit 1
        fi ;;
    esac
    mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"
    make_plist > "$PLIST"
    plutil -lint "$PLIST" >/dev/null
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "Scheduled: weekday $WEEKDAY at $(printf '%02d:%02d' "$HOUR" "$MINUTE"). Log: $LOGDIR/headless.log"
    echo "If the Mac is asleep then, it runs when the Mac next wakes. Test now:  scripts/schedule.sh run-now" ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"; echo "Schedule removed." ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      echo "Scheduled (label $LABEL)."; launchctl print "$DOMAIN/$LABEL" | grep -E "state|last exit code|runs" || true
    else echo "Not scheduled."; fi
    [ -f "$LOGDIR/headless.log" ] && { echo "--- last log lines ---"; tail -15 "$LOGDIR/headless.log"; } || echo "(no log yet)" ;;
  run-now)
    launchctl kickstart -k "$DOMAIN/$LABEL"; echo "Started. Watch: tail -f $LOGDIR/headless.log" ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
