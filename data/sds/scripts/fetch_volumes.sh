#!/usr/bin/env bash
# Download the SDS monograph PDFs (vols 1-65) from the IUPAC mirror and cache
# their text layer as text/SDS-N.txt (pdftotext -layout, pages separated by \f).
set -u
cd "$(dirname "$0")/.."
for n in $(seq 1 65); do
  pdf=pdfs/SDS-$n.pdf
  if [ ! -s "$pdf" ]; then
    code=$(curl -sSL -o "$pdf" -w '%{http_code}' "https://iupac.github.io/SolubilityDataSeries/volumes/SDS-$n.pdf")
    [ "$code" = 200 ] || { rm -f "$pdf"; echo "SDS-$n: $code (not on mirror)"; continue; }
  fi
  [ -s "text/SDS-$n.txt" ] || pdftotext -layout "$pdf" "text/SDS-$n.txt"
  echo "SDS-$n: $(pdfinfo "$pdf" | awk '/^Pages/{print $2}') pages, $(wc -c < text/SDS-$n.txt) chars"
done
