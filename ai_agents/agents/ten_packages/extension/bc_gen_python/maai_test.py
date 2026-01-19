import queue
from maai import Maai, MaaiInput, MaaiOutput
from pyaudio import PyAudio
import wave

mic = MaaiInput.Mic(mic_device_index=0)
zero = MaaiInput.Zero()

output = MaaiOutput.ConsoleBar()

maai = Maai(mode="bc", lang="jp", frame_rate=20, context_len_sec=20, audio_ch1=mic, audio_ch2=zero, device="cpu")
maai.start()

thresh: float = 0.5  # Threshold for backchannel detection
cooldown: int = 10

# Open the wave file
wf = wave.open("uhm.wav", "rb")

# Create a PyAudio instance
p = PyAudio()

# Open a stream with the same parameters as the wave file
stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True)

chunk = 1024

while True:
    
    result = maai.get_result()
    output.update(result)
    
    cooldown -= 1
    
    if result['p_bc'] > thresh and cooldown <= 0:
        cooldown = 10
        print(f"Backchannel detected with probability: {result['p_bc']:.2f}")
        
        data = wf.readframes(chunk)

        # Play the audio by writing data to the stream
        while data:
            stream.write(data)
            data = wf.readframes(chunk)
        
        wf.rewind()  # Reset the wave file to the beginning for the next playback
        