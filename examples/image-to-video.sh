#!/usr/bin/env bash
set -euo pipefail
: "${ARGOLINK_API_KEY:?set ARGOLINK_API_KEY first}"
BASE_URL="${ARGOLINK_BASE_URL:-https://api.argolink.io}"
IMAGE_URL="${1:?pass a public HTTPS storyboard image URL}"
VIDEO_JOB=$(curl -sS "$BASE_URL/v1/videos/generations" \
  -H "Authorization: Bearer ${ARGOLINK_API_KEY}" -H 'Content-Type: application/json' \
  -d "$(python3 - <<'PY' "$IMAGE_URL"
import json,sys
print(json.dumps({'model':'seedance-2.5','prompt':'Preserve image 1 composition. Slow camera push-in, gentle fabric movement, natural sound.', 'duration':5,'resolution':'720p','aspect_ratio':'16:9','reference_images':[{'url':sys.argv[1]}]}))
PY
)")
printf '%s\n' "$VIDEO_JOB"
