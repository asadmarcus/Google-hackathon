"""Download training CSV files into data/training/."""
import base64
import json
import subprocess
import sys
from pathlib import Path

OUT_DIR = Path(__file__).parent / "data" / "training"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def download_github_blob(repo: str, sha: str, dest_name: str):
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/blobs/{sha}"],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        print(f"ERROR fetching {dest_name}: {result.stderr}")
        return False
    blob = json.loads(result.stdout)
    raw = base64.b64decode(blob["content"].replace("\n", ""))
    dest = OUT_DIR / dest_name
    dest.write_bytes(raw)
    print(f"  OK {dest_name}  ({len(raw):,} bytes)")
    return True

print("Downloading training data...")

# FloodPrediction.csv — n-gauhar/Flood-prediction (GitHub, public)
download_github_blob(
    repo="n-gauhar/Flood-prediction",
    sha="66c15f0b6cb347f455bf29d94ec29e8ffe9f38cf",
    dest_name="FloodPrediction.csv",
)

print("\nDone. Files saved to:", OUT_DIR)
print("\nNote: Kaggle datasets (flood_prediction_dataset.csv, pakistan_flood_disasters.csv)")
print("require a Kaggle account. Download them manually from:")
print("  https://www.kaggle.com/datasets/naiyakhalid/flood-prediction-dataset")
print("  https://www.kaggle.com/datasets/alitaqishah/pakistan-flood-disasters-dataset")
print("and place them in:", OUT_DIR)
