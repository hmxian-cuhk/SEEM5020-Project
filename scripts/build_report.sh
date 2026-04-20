#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TEXMFVAR="/tmp/texmf-var"
mkdir -p "$TEXMFVAR"
cd "$REPO_ROOT/report"
pdflatex -interaction=nonstopmode -halt-on-error report.tex >/tmp/seem5020_report_build.log
pdflatex -interaction=nonstopmode -halt-on-error report.tex >>/tmp/seem5020_report_build.log
echo "$REPO_ROOT/report/report.pdf"
