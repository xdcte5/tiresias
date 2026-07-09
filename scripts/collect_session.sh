#!/usr/bin/env bash
# Guided capture of ONE labeled session for the Tiresias dataset.
#
# A "session" == you running one app/service for a few minutes. Each session becomes
# one flow-dump file whose name is the session id, so the training split can group by
# session (flows from one session never straddle train/test).
#
# ⚖️  Only capture your own traffic on your own network. See README scope section.
#
# Usage:
#   sudo ./scripts/collect_session.sh <iface> <class-hint> <seconds>
# Example (then go use YouTube for the duration):
#   sudo ./scripts/collect_session.sh wlan0 video_streaming 300
#
# The <class-hint> is only used to name the file; the actual label is derived later
# from each flow's TLS SNI by `tiresias-build-dataset`. Run several sessions per app
# across different times for a diverse dataset.
set -euo pipefail

IFACE="${1:?usage: collect_session.sh <iface> <class-hint> <seconds>}"
HINT="${2:?provide a class hint, e.g. video_streaming}"
SECONDS_DUR="${3:-300}"

TS="$(date +%Y%m%d-%H%M%S)"
OUT="data/flows/${HINT}__${TS}.parquet"

echo ">> Capturing on ${IFACE} for ${SECONDS_DUR}s -> ${OUT}"
echo ">> Start using the target app NOW. Ctrl-C to stop early."
tiresias-capture --iface "${IFACE}" --seconds "${SECONDS_DUR}" --out "${OUT}"
echo ">> Done. Build/refresh the dataset with:"
echo "     tiresias-build-dataset --flows-dir data/flows --out data/datasets/captured.parquet"
