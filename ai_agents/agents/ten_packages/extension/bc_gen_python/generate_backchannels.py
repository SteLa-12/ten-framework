import os
from openai import OpenAI
import dotenv

dotenv.load_dotenv('../../../../.env')


# Initialize the OpenAI client
# Ensure your OPENAI_API_KEY is set in your environment variables
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_backchannels():
    # 1. Define your backchannels
    # Note: Punctuation heavily influences intonation. 
    # "Mm-hm." sounds like agreement. "Mm-hm?" sounds like a question.
    backchannels = [
        "Mm-hm.",
        "Yeah.",
        "Right.",
        "I see.",
        "Uh-huh.",
        "Go on.",
        "Sure."
    ]

    # 2. Settings
    output_folder = "backchannel_audio_male"
    voice_actor = "alloy" # Options: alloy, echo, fable, onyx, nova, shimmer
    model_version = "tts-1" # tts-1 is faster/snappier than tts-1-hd

    # Create output directory if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created folder: {output_folder}")

    print(f"Generating {len(backchannels)} files using voice '{voice_actor}'...")

    # 3. Loop through list and generate audio
    for text in backchannels:
        try:
            # Create a clean filename (remove punctuation for the file system)
            filename = text.replace(".", "").replace("-", "").replace(" ", "_").lower()
            file_path = os.path.join(output_folder, f"{filename}.wav")

            print(f"Generating: '{text}' -> {file_path}")

            response = client.audio.speech.create(
                model=model_version,
                voice=voice_actor,
                input=text,
                response_format="wav"  # Explicitly requesting WAV format
            )

            # Stream the response to a file
            response.stream_to_file(file_path)

        except Exception as e:
            print(f"Error generating '{text}': {e}")

    print("\nDone! All files generated.")

if __name__ == "__main__":
    generate_backchannels()