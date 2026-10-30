#!/bin/sh
set -eu

data_dir="${ARIADNE_DATA_DIR:-/app/data/processed}"
mkdir -p "$data_dir"

if [ ! -s "$data_dir/graph.json" ] || [ ! -s "$data_dir/manifest.json" ]; then
    python -m scripts.prepare_data --output "$data_dir"
fi
if [ ! -s "$data_dir/model.json" ] || [ ! -s "$data_dir/evaluation.json" ]; then
    python -m scripts.evaluate --data-dir "$data_dir"
fi
if [ "${ARIADNE_GRAPH_BACKEND:-memory}" = "neo4j" ]; then
    python -m scripts.load_neo4j
fi

exec "$@"
