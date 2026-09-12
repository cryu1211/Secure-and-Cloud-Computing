#!/usr/bin/env python3
import csv
import sys
from collections import defaultdict

import matplotlib.pyplot as plt


def read_timings(filename):
    timings = defaultdict(lambda: {"real": [], "user": [], "sys": []})
    with open(filename, newline="") as data_file:
        for row in csv.DictReader(data_file):
            program = row["program"]
            for metric in ("real", "user", "sys"):
                timings[program][metric].append(float(row[metric]))
    return timings


def cdf(values):
    ordered = sorted(values)
    probabilities = [(index + 1) / len(ordered) for index in range(len(ordered))]
    return ordered, probabilities


def plot_cdf(timings, metric, title, ylabel, output_file):
    plt.figure(figsize=(8, 5))
    for program, measurements in sorted(timings.items()):
        x_values, y_values = cdf(measurements[metric])
        plt.step(x_values, y_values, where="post", label=program)

    plt.xlabel("Time (seconds)")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_file, dpi=160)
    plt.close()


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "timings.csv"
    timings = read_timings(input_file)
    if not timings:
        raise SystemExit("No timing data found")

    plot_cdf(
        timings,
        "real",
        "CDF of Execution Time",
        "Fraction of runs <= time",
        "execution_time_cdf.png",
    )
    plot_cdf(
        timings,
        "user",
        "CDF of User-Space Time",
        "Fraction of runs <= time",
        "user_time_cdf.png",
    )

    # Kernel time is plotted alongside user time because both are CPU-time metrics.
    plt.figure(figsize=(8, 5))
    for program, measurements in sorted(timings.items()):
        for metric, label in (("user", "user"), ("sys", "kernel")):
            x_values, y_values = cdf(measurements[metric])
            plt.step(x_values, y_values, where="post", label=f"{program} {label}")

    plt.xlabel("CPU time (seconds)")
    plt.ylabel("Fraction of runs <= time")
    plt.title("CDF of User-Space and Kernel-Space Time")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig("user_kernel_time_cdf.png", dpi=160)
    plt.close()

    print("Created execution_time_cdf.png")
    print("Created user_time_cdf.png")
    print("Created user_kernel_time_cdf.png")


if __name__ == "__main__":
    main()
