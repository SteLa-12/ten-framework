import wave
import sys
import os

def pcm_to_wav(pcm_file_path, wav_file_path, channels=1, rate=44100, sample_width=2):
    """
    Converts a raw PCM file to a WAV file.
    
    Args:
        pcm_file_path (str): Path to the input raw PCM file.
        wav_file_path (str): Path to the output WAV file.
        channels (int): Number of channels (1=Mono, 2=Stereo). Default is 1.
        rate (int): Sampling rate in Hz (e.g., 44100, 16000). Default is 44100.
        sample_width (int): Sample width in bytes (1=8-bit, 2=16-bit). Default is 2.
    """
    
    # Check if input file exists
    if not os.path.exists(pcm_file_path):
        print(f"Error: Input file '{pcm_file_path}' not found.")
        return

    try:
        # Open the raw PCM file in binary read mode
        with open(pcm_file_path, 'rb') as pcm_file:
            pcm_data = pcm_file.read()
            
        # Open the WAV file in binary write mode
        with wave.open(wav_file_path, 'wb') as wav_file:
            # Set the WAV parameters
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(rate)
            
            # Write the PCM data to the WAV file
            wav_file.writeframes(pcm_data)
            
        print(f"Successfully converted '{pcm_file_path}' to '{wav_file_path}'")
        print(f"Settings: {rate}Hz, {channels} Channel(s), {sample_width*8}-bit")

    except Exception as e:
        print(f"An error occurred during conversion: {e}")

if __name__ == "__main__":
    # --- CONFIGURATION ---
    # You can change these values based on your specific PCM file format
    INPUT_FILE = "openai_asr_in.pcm"
    OUTPUT_FILE = "output.wav"
    CHANNELS = 1           # 1 for Mono, 2 for Stereo
    SAMPLE_RATE = 16000    # Common rates: 44100, 48000, 16000, 8000
    SAMPLE_WIDTH = 2       # 2 bytes = 16-bit resolution
    # ---------------------

    # Check if a filename was provided via command line, otherwise use defaults
    if len(sys.argv) > 1:
        INPUT_FILE = sys.argv[1]
        # Automatically generate output filename if only input is provided
        if len(sys.argv) > 2:
            OUTPUT_FILE = sys.argv[2]
        else:
            filename, ext = os.path.splitext(INPUT_FILE)
            OUTPUT_FILE = f"{filename}.wav"

    print("Starting conversion...")
    pcm_to_wav(INPUT_FILE, OUTPUT_FILE, CHANNELS, SAMPLE_RATE, SAMPLE_WIDTH)