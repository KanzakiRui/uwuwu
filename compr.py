#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import time
import re
from pathlib import Path


def check_ffmpeg():
    """Check if FFmpeg is installed and available in PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except FileNotFoundError:
        return False


def get_video_info(video_path):
    """Get video information using FFmpeg."""
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-hide_banner"
    ]
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    
    # Parse the output to extract video information
    info = {}
    output = result.stderr
    
    # Extract resolution
    resolution_search = re.search(r'(\d{3,4}x\d{3,4})', output)
    if resolution_search:
        info['resolution'] = resolution_search.group(1)
    
    # Extract duration
    duration_search = re.search(r'Duration: (\d{2}:\d{2}:\d{2}\.\d{2})', output)
    if duration_search:
        info['duration'] = duration_search.group(1)
    
    # Check if it's HEVC/H.265
    if 'HEVC' in output or 'hevc' in output or 'h265' in output or 'H.265' in output:
        info['codec'] = 'HEVC'
    elif 'h264' in output or 'H.264' in output or 'AVC' in output:
        info['codec'] = 'H.264'
    else:
        info['codec'] = 'Unknown'
    
    return info


def compress_video(input_file, output_file, resolution='1080', preset='medium', crf=23, audio_bitrate='128k', use_gpu=True):
    """
    Compress a video file using FFmpeg with special handling for HEVC sources.
    
    Args:
        input_file (str): Path to the input video file
        output_file (str): Path to save the compressed video
        resolution (str): Target resolution, either '1080' or '720'
        preset (str): FFmpeg preset (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)
        crf (int): Constant Rate Factor (0-51, lower is better quality but larger file)
        audio_bitrate (str): Audio bitrate (e.g., '128k', '192k', '256k')
        use_gpu (bool): Whether to try using GPU acceleration
    
    Returns:
        bool: True if compression was successful, False otherwise
    """
    # Get video info to check if it's HEVC
    video_info = get_video_info(input_file)
    is_hevc = video_info.get('codec') == 'HEVC'
    
    # Set height based on resolution, width will be calculated automatically to maintain aspect ratio
    height = '1080' if resolution == '1080' else '720'
    
    # Base command parts
    input_args = [
        "ffmpeg",
        "-y",  # Overwrite output file if it exists
    ]
    
    # Try to use GPU acceleration if requested
    hw_encoders = []
    if use_gpu:
        # Try to detect available hardware encoders
        try:
            encoders_output = subprocess.check_output(["ffmpeg", "-encoders"], stderr=subprocess.STDOUT, universal_newlines=True)
            
            # Check for NVIDIA GPU encoder
            if "h264_nvenc" in encoders_output:
                hw_encoders.append("h264_nvenc")
            # Check for AMD GPU encoder
            if "h264_amf" in encoders_output:
                hw_encoders.append("h264_amf")
            # Check for Intel Quick Sync encoder
            if "h264_qsv" in encoders_output:
                hw_encoders.append("h264_qsv")
            # Check for VA-API encoder (Linux)
            if "h264_vaapi" in encoders_output:
                hw_encoders.append("h264_vaapi")
            # Check for VideoToolbox encoder (macOS)
            if "h264_videotoolbox" in encoders_output:
                hw_encoders.append("h264_videotoolbox")
                
            if hw_encoders:
                print(f"Detected hardware encoders: {', '.join(hw_encoders)}")
            else:
                print("No hardware encoders detected, using software encoding")
        except:
            print("Could not detect hardware encoders, using software encoding")
    
    # For HEVC sources, add special handling
    if is_hevc:
        print("Detected HEVC/H.265 source video. Using special handling...")
        input_args.extend([
            "-hwaccel", "auto",  # Try to use hardware acceleration if available
        ])
    
    # Complete the command
    cmd = input_args + [
        "-i", input_file,
        "-vf", f"scale=-1:{height}",  # Scale to target height, maintain aspect ratio
    ]
    
    # Add encoder settings
    if hw_encoders and use_gpu:
        # Use the first available hardware encoder
        hw_encoder = hw_encoders[0]
        print(f"Using hardware encoder: {hw_encoder}")
        
        if hw_encoder == "h264_nvenc":
            # NVIDIA GPU settings
            cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "p4",  # NVIDIA presets are different
                "-rc:v", "vbr",
                "-qmin", "0",
                "-qmax", "51",
                "-qp", str(crf),
            ])
        elif hw_encoder == "h264_amf":
            # AMD GPU settings
            cmd.extend([
                "-c:v", "h264_amf",
                "-quality", "balanced",
                "-rc", "cqp",
                "-qp_i", str(crf),
                "-qp_p", str(crf),
            ])
        elif hw_encoder == "h264_qsv":
            # Intel Quick Sync settings
            cmd.extend([
                "-c:v", "h264_qsv",
                "-preset", "medium",
                "-global_quality", str(crf),
            ])
        elif hw_encoder == "h264_vaapi":
            # VA-API (Linux) settings
            cmd.extend([
                "-c:v", "h264_vaapi",
                "-qp", str(crf),
            ])
        elif hw_encoder == "h264_videotoolbox":
            # VideoToolbox (macOS) settings
            cmd.extend([
                "-c:v", "h264_videotoolbox",
                "-q:v", str(crf),
            ])
    else:
        # Standard software encoding
        cmd.extend([
            "-c:v", "libx264",            # Use H.264 codec for output
            "-preset", preset,            # Compression preset
            "-crf", str(crf),             # Quality factor
        ])
    
    # Add common settings
    cmd.extend([
        "-c:a", "aac",                # Audio codec
        "-b:a", audio_bitrate,        # Audio bitrate
        "-movflags", "+faststart",    # Optimize for web streaming
        "-max_muxing_queue_size", "1024",  # Prevent muxing errors with complex videos
        output_file
    ])
    
    print(f"Starting compression of {input_file} to {resolution}p...")
    print(f"Command: {' '.join(cmd)}")
    
    start_time = time.time()
    
    try:
        # Run the FFmpeg command
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        # Store all output for error reporting
        all_output = []
        
        # Display progress
        for line in process.stdout:
            line = line.strip()
            all_output.append(line)
            if "frame=" in line and "fps=" in line and "time=" in line:
                sys.stdout.write("\r" + line)
                sys.stdout.flush()
        
        process.wait()
        
        if process.returncode == 0:
            elapsed_time = time.time() - start_time
            print(f"\nCompression completed successfully in {elapsed_time:.2f} seconds.")
            
            # Get file sizes
            input_size = os.path.getsize(input_file) / (1024 * 1024)  # MB
            output_size = os.path.getsize(output_file) / (1024 * 1024)  # MB
            reduction = (1 - (output_size / input_size)) * 100
            
            print(f"Input file size: {input_size:.2f} MB")
            print(f"Output file size: {output_size:.2f} MB")
            print(f"Size reduction: {reduction:.2f}%")
            
            return True
        else:
            print(f"\nFFmpeg returned error code {process.returncode}")
            print("\nError details:")
            # Print the last 10 lines of output which often contain the error
            for line in all_output[-10:]:
                print(line)
                
            # If specific errors are found, suggest solutions
            error_text = '\n'.join(all_output)
            if "No such file or directory" in error_text:
                print("\nPossible solution: Check that the input file path is correct and accessible")
            elif "Invalid data found when processing input" in error_text:
                print("\nPossible solution: The input file may be corrupted or in an unsupported format")
            elif "Error while opening encoder" in error_text:
                print("\nPossible solution: The selected encoder is not available. Try without GPU acceleration using --no-gpu")
            
            return False
            
    except Exception as e:
        print(f"\nError during compression: {str(e)}")
        return False


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Compress 4K video to 1080p or 720p (with special HEVC handling)")
    parser.add_argument("--input", "-i", required=True, help="Input video file path")
    parser.add_argument("--output", "-o", required=True, help="Output video file path")
    parser.add_argument("--resolution", "-r", choices=["1080", "720"], default="1080", help="Target resolution")
    parser.add_argument("--preset", "-p", default="medium", 
                        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
                        help="FFmpeg preset (slower = better compression)")
    parser.add_argument("--crf", "-c", type=int, default=23, help="Constant Rate Factor (0-51, lower is better quality)")
    parser.add_argument("--audio-bitrate", "-a", default="128k", help="Audio bitrate (e.g., '128k', '192k')")
    parser.add_argument("--force", "-f", action="store_true", help="Force overwrite output file if it exists")
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.isfile(args.input):
        print(f"Error: Input file '{args.input}' does not exist.")
        return 1
    
    # Check if FFmpeg is installed
    if not check_ffmpeg():
        print("Error: FFmpeg is not installed or not found in PATH.")
        print("Please install FFmpeg and make sure it's available in your system PATH.")
        return 1
    
    # Check if output file exists and --force not specified
    if os.path.exists(args.output) and not args.force:
        print(f"Error: Output file '{args.output}' already exists. Use --force to overwrite.")
        return 1
    
    # Get input video info
    print(f"Analyzing input video: {args.input}")
    video_info = get_video_info(args.input)
    if video_info:
        print(f"Resolution: {video_info.get('resolution', 'Unknown')}")
        print(f"Duration: {video_info.get('duration', 'Unknown')}")
        print(f"Codec: {video_info.get('codec', 'Unknown')}")
    
    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)
    
    # Compress video
    success = compress_video(
        args.input,
        args.output,
        resolution=args.resolution,
        preset=args.preset,
        crf=args.crf,
        audio_bitrate=args.audio_bitrate
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())