## Part 1: Thread Interleaving

### 1. Compile the program

From the `hw1` directory, run:

```bash
cd homework1/part1
make all
```

This creates the executable `prog` from `program.c`.

### 2. Run the experiment in the background

The script runs `prog` 1,000 times, records which thread finishes first, and saves the final counts to `results.txt`.

```bash
nohup bash get_interleaving.sh > execution.log 2>&1 &
```

The `nohup` command allows the experiment to continue after the SSH connection closes. The final `&` puts it in the background.

### 3. Monitor progress

View the progress log with:

```bash
tail -f execution.log
```

Stop viewing the log with `Ctrl+C`; this does not stop the experiment. To check whether it is still running:

```bash
pgrep -af get_interleaving.sh
```

When the experiment finishes, view the saved counts with:

```bash
cat results.txt
```

The output reports how many times `f1` finished first and how many times `f2` finished first.

### 4. Change the number of runs

The default is 1,000 runs. To change it, edit this line in `get_interleaving.sh`:

```bash
iterations=1000
```

The progress bar automatically adjusts to the selected number of iterations. Restore `iterations=1000` for the final experiment.

### 5. Interpretation

`f1` uses buffered `fprintf()` calls, while `f2` uses many direct `write()` system calls. The experiment is expected to show `f1` finishing first most of the time, but the ordering is not guaranteed because thread scheduling, CPU load, caching, and I/O activity can vary between runs.


## Part 2 Timing Measurements

### 1. Compile the programs

From the `hw1` directory, run:

```bash
cd homework1/part2
make all
```

This creates the executables `ver1` and `ver2`.

### 2. Run the measurements in the background

The measurement script runs each program 1,000 times and writes the results to `timings.csv`.

```bash
cd homework1/part2
nohup bash measure_times.sh > measurement.log 2>&1 &
```

The `nohup` command allows the measurement to continue after the SSH connection closes. The final `&` puts the process in the background.

### 3. Monitor progress

From `hw1/homework1/part2`, view the latest progress message with:

```bash
tail -f measurement.log
```

Stop viewing the log with `Ctrl+C`. This does not stop the measurement process.

To check whether the process is still running:

```bash
pgrep -af measure_times.sh
```


There should be 2,000 data rows plus the header:

```bash
wc -l timings.csv
```

### 4. Generate the CDF figures

After the measurement finishes, run from `hw1/homework1/part2`:

```bash
python3 plot_cdfs.py timings.csv
```

The script creates:

- `execution_time_cdf.png`: CDF of elapsed (`real`) execution time
- `user_time_cdf.png`: CDF of userspace (`user`) CPU time
- `user_kernel_time_cdf.png`: CDF comparison of userspace and kernel (`sys`) CPU time

### 5. Timing data format

`timings.csv` contains one row for every execution:

```text
program,run,real,user,sys
```

- `real`: total elapsed wall-clock time
- `user`: time spent executing in userspace
- `sys`: time spent executing in the kernel

The scripts use `/usr/bin/time` to collect these values. The CDF plots show the fraction of runs that completed within each measured time.

### 6. Optional shorter test

For a quick test, temporarily change this line in `measure_times.sh`:

```bash
iterations=1000
```

to a smaller value, such as:

```bash
iterations=10
```

Restore `iterations=1000` before collecting the final homework data.

