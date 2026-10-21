#!/usr/bin/env bash
# Download the SDS monograph PDFs (vols 1-65) from the IUPAC mirror and cache
# their text layer as text/SDS-N.txt (pdftotext -layout, pages separated by \f).
# Ground-truth volumes (status "mined" in volumes.csv) go to ground_truth/pdfs and
# ground_truth/text instead.
set -u
cd "$(dirname "$0")/../data"
mined=" $(awk -F, 'NR>1 && $NF ~ /^mined/{printf "%s ", $1}' volumes.csv)"
for n in $(seq 1 65); do
  dir=.
  case "$mined" in *" $n "*) dir=ground_truth ;; esac
  mkdir -p "$dir/pdfs" "$dir/text"
  pdf=$dir/pdfs/SDS-$n.pdf txt=$dir/text/SDS-$n.txt
  if [ ! -s "$pdf" ]; then
    code=$(curl -sSL -o "$pdf" -w '%{http_code}' "https://iupac.github.io/SolubilityDataSeries/volumes/SDS-$n.pdf")
    [ "$code" = 200 ] || { rm -f "$pdf"; echo "SDS-$n: $code (not on mirror)"; continue; }
  fi
  [ -s "$txt" ] || pdftotext -layout "$pdf" "$txt"
  echo "SDS-$n ($dir): $(pdfinfo "$pdf" | awk '/^Pages/{print $2}') pages, $(wc -c < "$txt") chars"
done
