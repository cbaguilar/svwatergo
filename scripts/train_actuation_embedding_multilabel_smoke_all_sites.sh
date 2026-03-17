#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export EPOCHS="${EPOCHS:-3}"
export EVAL_EVERY="${EVAL_EVERY:-1}"
export SITE_LIST="${SITE_LIST:-bluerock,pryorfarm,santateresa}"

bash "$SCRIPT_DIR/train_actuation_embedding_multilabel_all_sites.sh"
