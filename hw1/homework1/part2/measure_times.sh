#!/bin/bash

iterations=1000
output_file="timings.csv"
bar_width=40

printf 'program,run,real,user,sys\n' > "$output_file"

for program in ./ver1 ./ver2; do
    name=$(basename "$program")
    echo "Measuring $name ($iterations runs)..."

    for ((run = 1; run <= iterations; run++)); do
        timing=$({ /usr/bin/time -f '%e,%U,%S' "$program" >/dev/null; } 2>&1)
        printf '%s,%d,%s\n' "$name" "$run" "$timing" >> "$output_file"

        # Progress bar
        filled=$((run * bar_width / iterations))
        remaining=$((bar_width - filled))
        filled_bar=$(printf '%*s' "$filled" '' | tr ' ' '#')
        remaining_bar=$(printf '%*s' "$remaining" '')
        percent=$((run * 100 / iterations))
        printf '\r%s [%s%s] %d/%d (%d%%)' \
            "$name" "$filled_bar" "$remaining_bar" "$run" "$iterations" "$percent"
    done
    printf '\n'
done

echo "Timing data saved to $output_file"
