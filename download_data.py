"""Download C-MAPSS FD001 dataset from available sources."""
import urllib.request
import zipfile
import io
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "raw")
os.makedirs(DATA_DIR, exist_ok=True)

FILES = ["train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt"]

# List of known mirrors to try
SOURCES = [
    # PHM datasets S3 bucket (common academic mirror)
    {
        "name": "PHM S3",
        "type": "zip",
        "url": "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip",
    },
    # NASA ti.arc host
    {
        "name": "NASA ARC",
        "type": "zip",
        "url": "https://ti.arc.nasa.gov/c/6/",
    },
    # Kaggle datasets API (public)
    {
        "name": "GitHub ehsanaghaei",
        "type": "individual",
        "base": "https://raw.githubusercontent.com/ehsanaghaei/CMAPSS/main/",
    },
    {
        "name": "GitHub dsridaran",
        "type": "individual",
        "base": "https://raw.githubusercontent.com/dsridaran/Predictive_Maintenance/main/Data/",
    },
    {
        "name": "GitHub swagato-c",
        "type": "individual",
        "base": "https://raw.githubusercontent.com/swagato-c/predictive-maintenance-NASA-cmaps/master/Dataset/",
    },
]


def download_zip(url, name):
    """Download a zip file and extract FD001 files."""
    print(f"  Trying ZIP from {name}: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=60)
        zip_data = resp.read()
        print(f"  Downloaded {len(zip_data)} bytes")
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            names_in_zip = zf.namelist()
            print(f"  ZIP contains: {names_in_zip[:10]}...")
            
            for fname in FILES:
                # Find the file in the zip (may be in a subdirectory)
                matches = [n for n in names_in_zip if n.endswith(fname)]
                if not matches:
                    print(f"  {fname} not found in ZIP")
                    return False
                with zf.open(matches[0]) as src:
                    data = src.read()
                    with open(os.path.join(DATA_DIR, fname), "wb") as dst:
                        dst.write(data)
                    print(f"  Extracted {fname}: {len(data)} bytes")
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def download_individual(base, name):
    """Download individual files from a base URL."""
    print(f"  Trying individual files from {name}: {base}")
    for fname in FILES:
        url = base + fname
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = resp.read()
            with open(os.path.join(DATA_DIR, fname), "wb") as f:
                f.write(data)
            print(f"  {fname}: {len(data)} bytes OK")
        except Exception as e:
            print(f"  {fname}: FAILED ({e})")
            return False
    return True


def main():
    # Check if files already exist
    existing = [f for f in FILES if os.path.exists(os.path.join(DATA_DIR, f))]
    if len(existing) == 3:
        print("All FD001 files already present in data/raw/")
        return True
    
    print("Downloading C-MAPSS FD001 dataset...")
    
    for source in SOURCES:
        if source["type"] == "zip":
            if download_zip(source["url"], source["name"]):
                print(f"SUCCESS from {source['name']}")
                return True
        elif source["type"] == "individual":
            if download_individual(source["base"], source["name"]):
                print(f"SUCCESS from {source['name']}")
                return True
    
    print("ERROR: Could not download from any source.")
    print("Please download manually from https://data.nasa.gov/dataset/CMAPSS-Jet-Engine-Simulated-Data/ff5v-kfq6")
    print(f"Place train_FD001.txt, test_FD001.txt, and RUL_FD001.txt in {DATA_DIR}")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
