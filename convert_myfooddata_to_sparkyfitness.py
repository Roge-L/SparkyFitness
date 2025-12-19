#!/usr/bin/env python3
"""
Convert MyFoodData CSV to SparkyFitness CSV format.

Usage:
    python convert_myfooddata_to_sparkyfitness.py
"""

import csv
import sys

INPUT_FILE = "MyFoodData Nutrition Facts SpreadSheet Release 1.4 - SR Legacy and FNDDS.csv"
OUTPUT_FILE = "sparkyfitness_foods.csv"

# SparkyFitness required headers
SPARKYFITNESS_HEADERS = [
    "name",
    "brand",
    "is_custom",
    "shared_with_public",
    "is_quick_food",
    "serving_size",
    "serving_unit",
    "calories",
    "protein",
    "carbs",
    "fat",
    "saturated_fat",
    "polyunsaturated_fat",
    "monounsaturated_fat",
    "trans_fat",
    "cholesterol",
    "sodium",
    "potassium",
    "dietary_fiber",
    "sugars",
    "vitamin_a",
    "vitamin_c",
    "calcium",
    "iron",
    "is_default",
]

# Mapping from MyFoodData columns to SparkyFitness columns
# MyFoodData column name -> SparkyFitness column name
COLUMN_MAPPING = {
    "Name": "name",
    "Calories": "calories",
    "Protein (g)": "protein",
    "Carbohydrate (g)": "carbs",
    "Fat (g)": "fat",
    "Saturated Fats (g)": "saturated_fat",
    "Fatty acids, total polyunsaturated (mg)": "polyunsaturated_fat",  # Note: mg, needs conversion
    "Fatty acids, total monounsaturated (mg)": "monounsaturated_fat",  # Note: mg, needs conversion
    "Trans Fatty Acids (g)": "trans_fat",
    "Cholesterol (mg)": "cholesterol",
    "Sodium (mg)": "sodium",
    "Potassium, K (mg)": "potassium",
    "Fiber (g)": "dietary_fiber",
    "Sugars (g)": "sugars",
    "Vitamin A, RAE (mcg)": "vitamin_a",  # Using RAE (mcg)
    "Vitamin C (mg)": "vitamin_c",
    "Calcium (mg)": "calcium",
    "Iron, Fe (mg)": "iron",
}


def clean_value(value, convert_mg_to_g=False):
    """Clean and convert a value from the CSV."""
    if value is None or value == "" or value == "NULL":
        return 0
    try:
        num = float(value)
        if convert_mg_to_g:
            num = num / 1000  # Convert mg to g
        return round(num, 2)
    except (ValueError, TypeError):
        return 0


def main():
    print(f"Reading from: {INPUT_FILE}")

    rows_processed = 0
    rows_written = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as infile, \
         open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as outfile:

        # Skip the first 3 header/info rows
        for _ in range(3):
            next(infile)

        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=SPARKYFITNESS_HEADERS)
        writer.writeheader()

        for row in reader:
            rows_processed += 1

            # Skip rows without a name
            name = row.get("Name", "").strip()
            if not name:
                continue

            # Build the SparkyFitness row
            sf_row = {
                "name": name,
                "brand": "USDA",  # Default brand
                "is_custom": "true",
                "shared_with_public": "false",
                "is_quick_food": "false",
                "serving_size": 100,  # MyFoodData uses 100g servings
                "serving_unit": "g",
                "is_default": "false",
            }

            # Map the nutrition columns
            sf_row["calories"] = clean_value(row.get("Calories"))
            sf_row["protein"] = clean_value(row.get("Protein (g)"))
            sf_row["carbs"] = clean_value(row.get("Carbohydrate (g)"))
            sf_row["fat"] = clean_value(row.get("Fat (g)"))
            sf_row["saturated_fat"] = clean_value(row.get("Saturated Fats (g)"))
            sf_row["trans_fat"] = clean_value(row.get("Trans Fatty Acids (g)"))
            sf_row["cholesterol"] = clean_value(row.get("Cholesterol (mg)"))
            sf_row["sodium"] = clean_value(row.get("Sodium (mg)"))
            sf_row["potassium"] = clean_value(row.get("Potassium, K (mg)"))
            sf_row["dietary_fiber"] = clean_value(row.get("Fiber (g)"))
            sf_row["sugars"] = clean_value(row.get("Sugars (g)"))
            sf_row["vitamin_a"] = clean_value(row.get("Vitamin A, RAE (mcg)"))
            sf_row["vitamin_c"] = clean_value(row.get("Vitamin C (mg)"))
            sf_row["calcium"] = clean_value(row.get("Calcium (mg)"))
            sf_row["iron"] = clean_value(row.get("Iron, Fe (mg)"))

            # Convert mg to g for poly/mono fats
            sf_row["polyunsaturated_fat"] = clean_value(
                row.get("Fatty acids, total polyunsaturated (mg)"),
                convert_mg_to_g=True
            )
            sf_row["monounsaturated_fat"] = clean_value(
                row.get("Fatty acids, total monounsaturated (mg)"),
                convert_mg_to_g=True
            )

            writer.writerow(sf_row)
            rows_written += 1

            if rows_written % 1000 == 0:
                print(f"  Processed {rows_written} foods...")

    print(f"\nDone!")
    print(f"  Rows processed: {rows_processed}")
    print(f"  Foods written: {rows_written}")
    print(f"  Output file: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
