#!/usr/bin/env bash
# Toggle DEBUG_WEBHOOK_ENABLED in server/.env. Used by `just debug-on/off/status`.
#
# Idempotent — running `on` twice doesn't duplicate the line.
# Creates server/.env if absent. Preserves other lines unchanged.
#
# Usage:
#   scripts/toggle_debug_webhook.sh on
#   scripts/toggle_debug_webhook.sh off
#   scripts/toggle_debug_webhook.sh status

set -euo pipefail

ACTION="${1:-status}"
ENV_FILE="server/.env"
KEY="DEBUG_WEBHOOK_ENABLED"

_ensure_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        mkdir -p "$(dirname "$ENV_FILE")"
        : > "$ENV_FILE"
    fi
}

_current_value() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "(unset)"
        return
    fi
    local line
    line=$(grep -E "^${KEY}=" "$ENV_FILE" | tail -1 || true)
    if [[ -z "$line" ]]; then
        echo "(unset)"
    else
        echo "${line#${KEY}=}"
    fi
}

_set_value() {
    local target="$1"
    _ensure_file
    if grep -qE "^${KEY}=" "$ENV_FILE"; then
        # Replace in place. Use a tmp file for portability across sed variants.
        local tmp
        tmp=$(mktemp)
        awk -v k="${KEY}" -v v="${target}" \
            '{ if ($0 ~ "^" k "=") print k "=" v; else print $0 }' \
            "$ENV_FILE" > "$tmp"
        mv "$tmp" "$ENV_FILE"
    else
        # Append. Include a trailing newline if the file lacks one.
        if [[ -s "$ENV_FILE" ]] && [[ "$(tail -c1 "$ENV_FILE")" != "" ]]; then
            printf "\n" >> "$ENV_FILE"
        fi
        printf "%s=%s\n" "${KEY}" "${target}" >> "$ENV_FILE"
    fi
}

_url_status() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "not set"
        return
    fi
    local line
    line=$(grep -E "^DEBUG_WEBHOOK_URL=" "$ENV_FILE" | tail -1 || true)
    if [[ -z "$line" ]]; then
        echo "not set"
    elif [[ "$line" == "DEBUG_WEBHOOK_URL=" ]]; then
        echo "empty"
    else
        echo "set"
    fi
}

case "$ACTION" in
    on)
        _set_value "true"
        echo "DEBUG_WEBHOOK_ENABLED=true ($ENV_FILE)"
        echo "Note: backend service restart required for the change to take effect."
        if [[ "$(_url_status)" == "not set" || "$(_url_status)" == "empty" ]]; then
            echo "Warning: DEBUG_WEBHOOK_URL is $(_url_status) — channel will no-op until you populate it in $ENV_FILE."
        fi
        ;;
    off)
        _set_value "false"
        echo "DEBUG_WEBHOOK_ENABLED=false ($ENV_FILE)"
        echo "Note: backend service restart required for the change to take effect."
        ;;
    status)
        printf "DEBUG_WEBHOOK_ENABLED=%s\n" "$(_current_value)"
        printf "DEBUG_WEBHOOK_URL=%s\n" "$(_url_status)"
        ;;
    *)
        echo "usage: $0 {on|off|status}" >&2
        exit 2
        ;;
esac
