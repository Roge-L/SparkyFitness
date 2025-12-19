#!/usr/bin/env python3
"""
Split the large food CSV into smaller batch files.
"""

import csv
import os

INPUT_FILE = "sparkyfitness_foods.csv"
OUTPUT_DIR = "sparkyfitness_foods_batches"
BATCH_SIZE = 2000  # Foods per file

def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(INPUT_FILE, "r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        headers = reader.fieldnames

        batch_num = 1
        batch_rows = []

        for row in reader:
            batch_rows.append(row)

            if len(batch_rows) >= BATCH_SIZE:
                write_batch(batch_num, headers, batch_rows)
                batch_num += 1
                batch_rows = []

        # Write remaining rows
        if batch_rows:
            write_batch(batch_num, headers, batch_rows)

    print(f"\nDone! Created {batch_num} batch files in {OUTPUT_DIR}/")
    print(f"Import them one at a time in order.")

def write_batch(batch_num, headers, rows):
    filename = f"{OUTPUT_DIR}/batch_{batch_num:02d}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Created {filename} ({len(rows)} foods)")

if __name__ == "__main__":
    main()
