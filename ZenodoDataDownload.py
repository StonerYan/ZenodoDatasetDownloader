import requests
import os
import sys
import time
import re
from urllib.parse import urlparse

# Try to import tqdm for progress bar, otherwise define a simple alternative
try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, total=None, unit='B', unit_scale=True, desc=None, disable=False, initial=0):
            self.total = total
            self.n = initial
            self.desc = desc
            self.last_print = 0

        def update(self, n=1):
            self.n += n
            current_time = time.time()
            if current_time - self.last_print > 1 or self.n == self.total:
                print(f"\r{self.desc}: {self.n}/{self.total} bytes downloaded", end="")
                self.last_print = current_time
        
        def close(self):
            print()

def get_record_id(input_str):
    """
    Extract Zenodo Record ID from input URL or string
    Example: https://zenodo.org/record/1234567 -> 1234567
    """
    input_str = input_str.strip()
    # Match pure numeric ID
    if input_str.isdigit():
        return input_str
    
    # Match /record/1234567 or /records/1234567
    match = re.search(r'zenodo\.org/record/(\d+)', input_str)
    if match:
        return match.group(1)
    
    match = re.search(r'zenodo\.org/records/(\d+)', input_str)
    if match:
        return match.group(1)
        
    return None

def get_record_metadata(record_id):
    """
    Get Zenodo record metadata
    """
    api_url = f"https://zenodo.org/api/records/{record_id}"
    print(f"Fetching metadata: {api_url}")
    try:
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch metadata: {e}")
        return None

def download_file(url, filename, output_dir, expected_size=None, max_retries=5):
    """
    Download a single file with resume support
    """
    filepath = os.path.join(output_dir, filename)
    
    # Check local file size
    initial_pos = 0
    if os.path.exists(filepath):
        initial_pos = os.path.getsize(filepath)
        if expected_size and initial_pos == expected_size:
            print(f"File exists and size matches, skipping: {filename}")
            return True
        elif expected_size and initial_pos > expected_size:
            print(f"Local file larger than expected, redownloading: {filename}")
            initial_pos = 0
            os.remove(filepath)
        else:
            print(f"Found incomplete download, resuming from {initial_pos} bytes: {filename}")

    mode = 'ab' if initial_pos > 0 else 'wb'
    headers = {}
    if initial_pos > 0:
        headers['Range'] = f'bytes={initial_pos}-'

    retry_count = 0
    while retry_count < max_retries:
        try:
            with requests.get(url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                
                # Get total size
                total_size = int(r.headers.get('content-length', 0))
                if initial_pos > 0:
                    # If resuming, content-length is usually the remaining size
                    # But if it's a fresh download, it's the total size
                    # Note: If server supports Range, it returns 206 Partial Content
                    if r.status_code == 206:
                        total_size += initial_pos
                    elif r.status_code == 200:
                        # Server doesn't support Range or file changed, restart download
                        print("Server does not support resume or file changed, restarting download...")
                        initial_pos = 0
                        mode = 'wb'
                        total_size = int(r.headers.get('content-length', 0))

                # Progress bar
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename, initial=initial_pos) as pbar:
                    with open(filepath, mode) as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
            
            # Verify download completion
            if expected_size and os.path.getsize(filepath) != expected_size:
                raise Exception("File size mismatch after download")
            
            print(f"Download complete: {filename}")
            return True

        except Exception as e:
            retry_count += 1
            print(f"\nDownload error ({retry_count}/{max_retries}): {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)
            
            # Update header for next loop with latest file size
            if os.path.exists(filepath):
                initial_pos = os.path.getsize(filepath)
                headers['Range'] = f'bytes={initial_pos}-'
                mode = 'ab'
            else:
                initial_pos = 0
                headers = {}
                mode = 'wb'

    print(f"File {filename} failed to download after max retries.")
    return False

def main():
    print("=== Zenodo Dataset Downloader ===")
    user_input = input("Enter Zenodo URL or Record ID (e.g., https://zenodo.org/record/1234567): ").strip()
    
    record_id = get_record_id(user_input)
    if not record_id:
        print("Cannot identify Record ID, please check your input.")
        return

    print(f"Detected Record ID: {record_id}")
    
    metadata = get_record_metadata(record_id)
    if not metadata:
        return

    # Get user filter requirement
    filter_keyword = input("Enter filename filter keyword (optional, e.g., 'GLOBAL', leave empty to download all): ").strip()

    title = metadata.get('metadata', {}).get('title', 'Untitled_Dataset')
    # Clean illegal characters in filename
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
    output_dir = os.path.join(os.getcwd(), f"Zenodo_{record_id}_{safe_title}")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created download directory: {output_dir}")
    else:
        print(f"Using download directory: {output_dir}")

    files = metadata.get('files', [])
    print(f"Found {len(files)} files.")

    global_pass = 1
    while True:
        all_downloaded = True
        files_to_download_count = 0
        
        print(f"\n=== Starting download pass {global_pass} ===")

        for file_info in files:
            # Zenodo API response structure may change, handle compatibility
            # Old API: 'links': {'self': '...'}, 'key': 'filename'
            # New API: 'links': {'content': '...'}, 'key': 'filename' (API v1) 
            # Sometimes it is 'filename' field
            
            filename = file_info.get('key') or file_info.get('filename')
            download_url = file_info.get('links', {}).get('self') or file_info.get('links', {}).get('content')
            size = file_info.get('size')

            if not filename or not download_url:
                print(f"Skipping unparseable file info: {file_info}")
                continue

            if filter_keyword and filter_keyword.lower() not in filename.lower():
                # print(f"Skipping file not matching filter: {filename}")
                continue
            
            files_to_download_count += 1

            # Quick check if completed before calling download_file to avoid excessive logs
            filepath = os.path.join(output_dir, filename)
            if os.path.exists(filepath):
                initial_pos = os.path.getsize(filepath)
                if size and initial_pos == size:
                    # print(f"File exists and size matches, skipping: {filename}")
                    continue

            print(f"\nPreparing to download: {filename} (Size: {size} bytes)")
            success = download_file(download_url, filename, output_dir, expected_size=size)
            if not success:
                print(f"File {filename} failed, will retry in next pass.")
                all_downloaded = False
        
        if files_to_download_count == 0:
             print("No matching files found.")
             break

        if all_downloaded:
            print(f"\nAll {files_to_download_count} files downloaded successfully!")
            break
        else:
            print(f"\nPass {global_pass} completed with failures. Retrying in 10 seconds...")
            time.sleep(10)
            global_pass += 1

    print("\nAll tasks completed.")

if __name__ == "__main__":
    main()
