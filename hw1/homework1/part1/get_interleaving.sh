#! /bin/bash

# Configuration
iterations=1000
f1_first=0
f2_first=0
output_file="results.txt"

# Clear previous results
> "$output_file"

for i in $(seq 1 $iterations); do
    output=$(./prog)

    if [[ "$output" == "f1"* ]]; then
        ((f1_first++))
    elif [[ "$output" == "f2"* ]]; then
        ((f2_first++))
    fi

    # Progress bar
    bar=$((i * 50 / iterations))
    printf "\rProgress: [%-50s] %d%%" "$(printf '#%.0s' {1..$bar})" "$((i * 100 / iterations))"
done

echo ""
echo "f1 finished first: $f1_first times" | tee -a "$output_file"
echo "f2 finished first: $f2_first times" | tee -a "$output_file"