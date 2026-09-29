#!/bin/bash
# Cloudera AI runs this once when the Application is deployed.
set -eu

if pip3 install -r requirements.txt; then
  exit 0
fi

echo "Full install failed. Retrying without the google-re2 build."
grep -v '^cel-python' requirements.txt > /tmp/requirements-no-cel.txt
pip3 install -r /tmp/requirements-no-cel.txt
pip3 install --no-deps "cel-python==0.4.0"
