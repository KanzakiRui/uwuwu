#!/usr/bin/env python3

import os
import sys
import time
import subprocess
from pathlib import Path
from multiprocessing import Process
import argparse
import logging
import re

# Ensure .cache directory exists
cache_dir = Path('.cache')
cache_dir.mkdir(parents=True, exist_ok=True)

# Set up logging
logging.basicConfig(filename=cache_dir / 'pigy.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def webui(command):
    logging.info(f"Starting webui with command: {command}")
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error starting webui: {e}")
    except Exception as e:
        logging.error(f"Unexpected error starting webui: {e}")

def pingy_in(local_port):
    logging.info(f"Starting SSH tunnel on port 80 and forwarding to localhost:{local_port}...")
    output_file = cache_dir / 'pigy.txt'
    
    # Method 1: Try with sshpass (if available)
    try:
        # Check if sshpass is available
        subprocess.run(['which', 'sshpass'], check=True, capture_output=True)
        logging.info("Using sshpass for authentication")
        subprocess.run(f'sshpass -p "0000" ssh -o StrictHostKeyChecking=no -p 80 -R0:localhost:{local_port} auth@a.pinggy.io > {output_file}', shell=True, check=True)
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.info("sshpass not available, trying alternative methods")
    
    # Method 2: Try with expect (if available)
    try:
        subprocess.run(['which', 'expect'], check=True, capture_output=True)
        logging.info("Using expect for authentication")
        expect_script = f'''
spawn ssh -o StrictHostKeyChecking=no -p 80 -R0:localhost:{local_port} auth@a.pinggy.io
expect "password:"
send "0000\\r"
expect eof
'''
        with open(cache_dir / 'expect_script.exp', 'w') as f:
            f.write(expect_script)
        subprocess.run(f'expect {cache_dir / "expect_script.exp"} > {output_file}', shell=True, check=True)
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.info("expect not available, trying pipe method")
    
    # Method 3: Try with echo pipe (simple method)
    try:
        logging.info("Using echo pipe for authentication")
        subprocess.run(f'echo "0000" | ssh -o StrictHostKeyChecking=no -p 80 -R0:localhost:{local_port} auth@a.pinggy.io > {output_file}', shell=True, check=True)
        return
    except subprocess.CalledProcessError as e:
        logging.error(f"Echo pipe method failed: {e}")
    
    # Method 4: Fallback to original method (no auth)
    try:
        logging.info("Trying without auth keyword as fallback...")
        subprocess.run(f'ssh -o StrictHostKeyChecking=no -p 80 -R0:localhost:{local_port} a.pinggy.io > {output_file}', shell=True, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"All methods failed: {e}")
    except Exception as e:
        logging.error(f"Unexpected error establishing SSH tunnel: {e}")

def pingy_out(local_port, timeout=30):
    start_time = time.time()
    output_file = cache_dir / 'pigy.txt'
    
    while time.time() - start_time < timeout:
        time.sleep(2)
        logging.info("Checking for URL...")
        try:
            with open(output_file, 'r') as file:
                content = file.read()
                logging.info(f"Raw file content length: {len(content)}")
                
                # Clean up ANSI escape sequences and control characters
                # Remove ANSI escape sequences
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                cleaned_content = ansi_escape.sub('', content)
                
                # Remove other control characters but keep newlines
                cleaned_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned_content)
                
                logging.info(f"Cleaned content: {cleaned_content}")
                
                # Look for tunnel URLs specifically (not dashboard URLs)
                tunnel_patterns = [
                    r'https?://[a-zA-Z0-9-]+\.a\.free\.pinggy\.link',  # Free tier format
                    r'https?://[a-zA-Z0-9-]+\.a\.pinggy\.link',       # Pro tier format
                    r'https?://[a-zA-Z0-9-]+\.pinggy\.link',          # Legacy format
                ]
                
                found_urls = []
                for pattern in tunnel_patterns:
                    urls = re.findall(pattern, cleaned_content)
                    found_urls.extend(urls)
                
                # Remove duplicates and filter out dashboard URLs
                unique_urls = []
                for url in found_urls:
                    if url not in unique_urls and 'dashboard.pinggy.io' not in url:
                        unique_urls.append(url)
                
                if unique_urls:
                    logging.info(f"Found tunnel URLs: {unique_urls}")
                    print(f'\nTunnel URLs:')
                    for url in unique_urls:
                        print(f'  {url}')
                    print()
                    return
                
                # If no tunnel URLs found, look for any pinggy URLs but exclude dashboard
                general_pattern = r'https?://[^\s\]]+(?:pinggy\.link|pinggy\.io)[^\s\]]*'
                all_urls = re.findall(general_pattern, cleaned_content)
                
                tunnel_urls = [url for url in all_urls if 'dashboard.pinggy.io' not in url]
                
                if tunnel_urls:
                    logging.info(f"Found URLs (fallback): {tunnel_urls}")
                    print(f'\nTunnel URLs:')
                    for url in tunnel_urls:
                        print(f'  {url}')
                    print()
                    return
                            
        except FileNotFoundError:
            logging.warning(f"File not found: {output_file}")
        except Exception as e:
            logging.error(f"Unexpected error reading file: {e}")
    
    logging.error("Timeout reached, URL not found.")
    print("\nTimeout reached, URL not found.\n")

def runn(webui_command, local_port):
    try:
        p_tun = Process(target=webui, args=(webui_command,))
        p_app = Process(target=pingy_in, args=(local_port,))
        p_url = Process(target=pingy_out, args=(local_port,))
        
        p_tun.start()
        p_app.start()
        p_url.start()
        
        p_tun.join()
        p_app.join()
        p_url.join()
    except KeyboardInterrupt:
        logging.info("^C")
        print("^C")
        os.system(f'rm -rf {cache_dir / "pigy.txt"}')
    finally:
        os.system(f'rm -rf {cache_dir / "pigy.txt"}')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run webui with SSH tunnel and URL extraction.")
    parser.add_argument('webui_command', type=str, help='Command to start the webui')
    parser.add_argument('local_port', type=int, help='Local port to forward to')
    
    args = parser.parse_args()
    runn(args.webui_command, args.local_port)