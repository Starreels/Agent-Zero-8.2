#!/bin/bash

set -e
set -o pipefail

# install playwright
bash /ins/install_playwright.sh "$@"

# searxng
bash /ins/install_searxng.sh "$@"
