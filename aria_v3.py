#!/usr/bin/env python3

import argparse
import os
import subprocess
import concurrent.futures
from urllib.parse import urlparse

def is_url(link):
    # Check if the link has a valid URL scheme
    parsed_link = urlparse(link)
    return parsed_link.scheme in ("http", "https")

def download_file(link, output_dir, civitai_token, huggingface_token):
    # Initialize filename to None
    filename = None

    # Handle specific URL modifications and headers
    if "huggingface.co" in link:
        link = link.replace("/blob/", "/resolve/")
        filename = os.path.basename(urlparse(link).path)
    elif "civitai.com" in link and civitai_token:
        link = f"{link}?token={civitai_token}"
    else:
        filename = os.path.basename(urlparse(link).path)

    output_file = os.path.join(output_dir, filename) if filename else None

    if output_file and os.path.exists(output_file):
        print(f"Skipping {output_file} as it already exists.")
        return

    headers = []
    if "huggingface.co" in link and huggingface_token:
        headers.append(f'Authorization: Bearer {huggingface_token}')

    # Prepare command for aria2c
    command = ['aria2c', '--console-log-level=error', '-c', '-x16', '-s16', '-k1M', '-j5', '-d', output_dir]
    if headers:
        command += ['--header'] + headers

    if filename:
        command += ['-o', filename]
    
    command.append(link)

    # Run the command
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f'Error downloading {link}: {e}')

def main():
    parser = argparse.ArgumentParser(description='Checkpoint/Safetensors downloader with authentication tokens.')
    parser.add_argument('-l', '--link', type=str, required=True, help='Input your file/folder link here (comma-separated or .txt file).')
    parser.add_argument('-d', '--outdir', type=str, default='~/', help='Input your directory path here.')
    parser.add_argument('-ct', '--civitai-token', type=str, help='Authentication token for Civitai.')
    parser.add_argument('-ht', '--huggingface-token', type=str, help='Authentication token for Hugging Face.')
    
    args = parser.parse_args()
    output_dir = os.path.expanduser(args.outdir)
    
    # Check if the input link is a .txt file and not a URL
    if args.link.endswith('.txt') and not is_url(args.link):
        if os.path.exists(args.link):
            # Directly call aria2c with -i argument for .txt input
            command = ['aria2c', '-i', args.link, '--console-log-level=error', '-c', '-x16', '-s16', '-k1M', '-j5', '-d', output_dir]
            try:
                subprocess.run(command, check=True)
            except subprocess.CalledProcessError as e:
                print(f'Error downloading from {args.link}: {e}')
        else:
            # Raise an error if .txt file is not found
            raise FileNotFoundError(f"The specified .txt file '{args.link}' was not found.")
    else:
        # Otherwise, process as list of URLs with concurrent downloading
        links = [link.strip() for link in args.link.split(',')]
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(download_file, link, output_dir, args.civitai_token, args.huggingface_token): link
                for link in links
            }
            for future in concurrent.futures.as_completed(futures):
                future.result()

if __name__ == "__main__":
    main()
