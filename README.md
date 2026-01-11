# Zenodo Dataset Downloader

A robust Python script to download datasets from [Zenodo](https://zenodo.org/) with support for breakpoint resumption (resume capability), automatic retries, and file filtering.

## Features

- **Resume Capability**: Automatically resumes interrupted downloads from where they left off.
- **Robustness**: Infinite retry loop ensures all files are downloaded even with unstable internet connections.
- **Filtering**: Option to download only files matching a specific keyword (e.g., "GLOBAL").
- **Ease of Use**: Simple command-line interface.

## Requirements

- Python 3.6+
- `requests`
- `tqdm` (optional, for progress bar)

Install dependencies:
```bash
pip install requests tqdm
```

## Usage

1. Run the script:
   ```bash
   python ZenodoDataDownload.py
   ```

2. Enter the Zenodo Record URL or ID when prompted:
   ```
   Enter Zenodo URL or Record ID: https://zenodo.org/record/1234567
   ```

3. (Optional) Enter a keyword to filter files:
   ```
   Enter filename filter keyword (optional, e.g., 'GLOBAL', leave empty to download all): 
   ```

The script will create a folder named `Zenodo_<RecordID>_<Title>` and download all matching files into it.

