import os
import platform
import re
import sys
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://download.blender.org/release/"

def detect_system():
    """Detects current operating system and architecture to match Blender file patterns."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if "windows" in system:
        os_type = "windows"
        arch_pattern = r"(windows.*x64|windows64|win64)"
        ext = ".zip"
    elif "darwin" in system:
        os_type = "macos"
        if "arm" in machine or "aarch64" in machine:
            arch_pattern = r"(macos.*arm64|macOS.*arm64)"
        else:
            arch_pattern = r"(macos.*x64|macOS.*x64|macOS.*x86_64)"
        ext = ".dmg"
    elif "linux" in system:
        os_type = "linux"
        arch_pattern = r"(linux.*x64|linux.*x86_64|linux64)"
        ext = ".tar.xz"
    else:
        sys.exit(f"Unsupported operating system: {system}")

    return {
        "os": os_type,
        "machine": machine,
        "arch_pattern": arch_pattern,
        "extension": ext
    }

def fetch_version_directories():
    """Scrapes all release directory names from the base server."""
    print("Fetching available versions...")
    try:
        response = requests.get(BASE_URL, timeout=15)
        response.raise_for_status()
    except requests.RequestException as err:
        sys.exit(f"Failed to fetch version index: {err}")

    soup = BeautifulSoup(response.text, "html.parser")
    versions = []

    # Matches folders like Blender2.80/, Blender3.6/, Blender4.2/, Blender5.0/
    dir_pattern = re.compile(r"^Blender(\d+\.\d+)/?$")
    for link in soup.find_all("a"):
        href = link.get("href", "")
        match = dir_pattern.match(href)
        if match:
            folder_name = href.strip("/")
            # Parse version tuple for sorting (e.g. 4.2 -> (4, 2))
            major, minor = map(int, match.group(1).split("."))
            versions.append(((major, minor), folder_name))

    # Sort numerically in ascending order
    versions.sort(key=lambda item: item[0])
    return [name for _, name in versions]

def fetch_matching_files(version_dir, sys_info):
    """Finds download links in the version folder that match the host OS."""
    dir_url = f"{BASE_URL}{version_dir}/"
    try:
        response = requests.get(dir_url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as err:
        sys.exit(f"Failed to fetch files for {version_dir}: {err}")

    soup = BeautifulSoup(response.text, "html.parser")
    matched_files = []

    for link in soup.find_all("a"):
        href = link.get("href", "")
        if href.endswith(sys_info["extension"]):
            if re.search(sys_info["arch_pattern"], href, re.IGNORECASE):
                matched_files.append((href, f"{dir_url}{href}"))

    return matched_files

def prompt_selection(options, item_name):
    """Displays numbered choices and collects user input."""
    for idx, opt in enumerate(options, 1):
        print(f"[{idx:>3}] {opt}")

    while True:
        choice = input(f"\nSelect {item_name} number (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            sys.exit("Cancelled.")
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice) - 1
        print("Invalid selection. Enter a valid number.")

def download_file(file_url, filename, output_dir="downloads"):
    """Streams file download and prints progress."""
    os.makedirs(output_dir, exist_ok=True)
    destination = os.path.join(output_dir, filename)

    print(f"\nStarting download: {filename}")
    print(f"Destination: {destination}")

    with requests.get(file_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total_size = int(r.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB chunks

        with open(destination, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        sys.stdout.write(f"\rProgress: {pct:5.1f}% [{mb_done:.1f} MB / {mb_total:.1f} MB]")
                    else:
                        mb_done = downloaded / (1024 * 1024)
                        sys.stdout.write(f"\rDownloaded: {mb_done:.1f} MB")
                    sys.stdout.flush()

    print("\nDownload complete!")

def main():
    sys_info = detect_system()
    print(f"Detected Platform: {sys_info['os']} ({sys_info['machine']})")
    print(f"Target format: *{sys_info['extension']}\n")

    # 1. Fetch & Choose Version Folder
    versions = fetch_version_directories()
    if not versions:
        sys.exit("No version directories found.")

    print(f"--- Available Blender Versions ({len(versions)} found) ---")
    selected_version_idx = prompt_selection(versions, "version")
    selected_folder = versions[selected_version_idx]

    # 2. Fetch & Match Files for Host Platform
    print(f"\nSearching matching files in {selected_folder}...")
    files = fetch_matching_files(selected_folder, sys_info)

    if not files:
        sys.exit(f"No compatible {sys_info['os']} ({sys_info['extension']}) files found in {selected_folder}.")

    # 3. Choose File (if multiple exist, e.g. patch releases like 4.2.0 vs 4.2.1)
    if len(files) == 1:
        chosen_filename, chosen_url = files[0]
    else:
        print(f"\n--- Compatible Builds Found ---")
        filenames = [f[0] for f in files]
        chosen_idx = prompt_selection(filenames, "build")
        chosen_filename, chosen_url = files[chosen_idx]

    # 4. Download
    download_file(chosen_url, chosen_filename)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(0)