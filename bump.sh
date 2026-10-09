#!/bin/bash
# Minden build új csomagnevet kap -> új alkalmazásként települ, nem frissítésként
n=$(grep -oP '^package.name = otcanalyzer\K[0-9]*' buildozer.spec)
n=$(( ${n:-1} + 1 ))
sed -i "s/^package.name = .*/package.name = otcanalyzer$n/; s/^title = .*/title = OTC Analyzer $n/" buildozer.spec
echo "Új csomagnév: otcanalyzer$n"
