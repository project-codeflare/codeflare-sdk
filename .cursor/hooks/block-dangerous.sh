#!/bin/bash
set -euo pipefail

input=$(cat)
command_str=$(echo "$input" | jq -r '.command // empty')

if echo "$command_str" | grep -qE 'git\s+push\s+.*--force|git\s+push\s+-f\b'; then
  echo '{
    "permission": "deny",
    "user_message": "Force-push blocked by project hook. Use a normal push or override manually.",
    "agent_message": "Hook denied force-push. Do not retry with --force."
  }'
  exit 0
fi

if echo "$command_str" | grep -qE '\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b'; then
  echo '{
    "permission": "deny",
    "user_message": "rm -rf blocked by project hook. Remove files individually or override manually.",
    "agent_message": "Hook denied rm -rf. Use targeted file removal instead."
  }'
  exit 0
fi

echo '{ "permission": "allow" }'
exit 0
