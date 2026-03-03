import numpy as np
from aubio import pitch
import time
from collections import deque
import enum
import wave
import asyncio
import random

from ten_runtime.async_ten_env import AsyncTenEnv

from pathlib import Path
from ten_runtime.audio_frame import AudioFrame
from ten_runtime.audio_frame import AudioFrameDataFmt
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class BackchannelType(enum.Enum):
    ASSESSMENT = "assessment"
    CONTINUER = "continuer"



class RealtimeBackchanneler:
    def __init__(self, ten_env: AsyncTenEnv,
            frame_rate: int = 16000,
            chunk_size: int = 160,
            silence_threshold: float = 0.015,
            pause_req_ms: int = 400,
            speech_req_ms: int = 1000,
            pitch_window_ms: int = 100,
            pitch_shift_hz: float = 30.0,
            bc_cooldown_ms: int = 1400
        ):

        self.ten_env = ten_env
        self.frame_rate = frame_rate
        self.chunk_size = chunk_size
        self.silence_threshold = silence_threshold
        self.pause_req_ms = pause_req_ms
        self.speech_req_ms = speech_req_ms
        self.pitch_window_ms = pitch_window_ms
        self.pitch_shift_hz = pitch_shift_hz
        self.bc_cooldown_ms = bc_cooldown_ms

        # Initialize Real-time Pitch Tracker
        self.pitch_detector = pitch("yin", 2048, chunk_size, frame_rate)
        self.pitch_detector.set_unit("Hz")
        self.pitch_detector.set_silence(-40)

        # State Tracking
        self.is_speaking: bool = False
        self.speech_start_time: int = 0
        self.silence_start_time: int = 0
        self.last_bc_time: int = 0
        self.backchannel_opportunity: bool = False
        self.time_since_bop: int = 0
        self.latest_bc_class: BackchannelType | None = None

        # Calculate how many chunks fit into 100ms (100ms / 32ms ≈ 3 chunks)
        buffer_len = max(1, int((self.pitch_window_ms / 1000.0) / (self.chunk_size / self.frame_rate)))
        self.pitch_buffer = deque(maxlen=buffer_len)

        # Latched states at the moment speech ends
        self.pitch_valid_at_speech_end = False
        self.speech_duration_at_end = 0.0

        # Utterance buffer which gets filled as soon as results from the ASR module are available
        self.utterance_buffer: str = ""

        # Load backchannel prediction model and tokenizer
        # Load model and tokenizer from local folder
        model_dir = Path("ten_packages/extension/backchannel_generation_python/prediction-model")
        if not model_dir.exists():
            raise FileNotFoundError(f"Model folder not found: {model_dir.resolve()}")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(self.device)
        self.model.eval()
        self.send_backchannel_task: asyncio.Task | None = None

    def detect_pitch_variation(self, samples: bytearray) -> bool:
        """
        Detect wheter there is a pitch variation which is larger than the predefined threshold

        Args:
            audio_frame (AudioFrame): Current processed Audio Frame

        Returns:
            bool: True when a pitch rising or fall is detected which is higher than {self.pitch_shift_hz}
        """

        samples_np = np.frombuffer(samples, dtype=np.int16).astype(np.float32)

        pitch = self.pitch_detector(samples_np)[0]

        # Detect whether there was an actual pitch change (speech)
        if pitch > 0:
            # Add pitch value to buffer
            self.pitch_buffer.append(pitch)

        # Continuously evaluate if the current rolling 100ms window has a 30Hz drop/rise
        current_pitch_shift = 0.0
        if len(self.pitch_buffer) > 1:
            current_pitch_shift = max(self.pitch_buffer) - min(self.pitch_buffer)

        # Check if a pitch rising or fall is detected in the current window
        return current_pitch_shift >= self.pitch_shift_hz

    def set_talking(self, current_time: int) -> None:
        """
        Set current state to talking

        Args:
            current_time (int): Time at which function call is invoked
        """
        self.speech_start_time = current_time
        self.is_speaking = True

    def set_silence(self, current_time: int) -> None:
        """
        Set current state to silent

        Args:
            current_time (int): Time at which function call is invoked
        """
        self.silence_start_time = current_time
        self.is_speaking = False
        self.flush_utterance_buffer()

    def get_latest_speech_time(self, current_time: int) -> int:
        """
        Retrieve the duration of speech going on before this function call

        Args:
            current_time (int): current ms of audioframe

        Returns:
            int: amount of ms of speech. If -1 currently silent
        """

        if self.is_speaking:
            return current_time - self.speech_start_time

        return -1

    def get_latest_silence_time(self, current_time: int) -> int:
        """
        Retrieve the duration of silence going on before this function call

        Args:
            current_time (int): current ms of audioframe

        Returns:
            int: amount of ms of silence. If -1 currently talking
        """

        if not self.is_speaking:
            return current_time - self.silence_start_time

        return -1

    def get_time_since_latest_bc(self, current_time: int) -> int:
        """
        Retrieve the time in ms since the latest backchannel was outputted

        Args:
            current_time (int): current time of invoking the function

        Returns:
            int: amount of ms since latest backchannel
        """

        return current_time - self.last_bc_time

    def add_to_utterance_buffer(self, utterance: str) -> None:
        """
        Add a new utterance to the buffer

        Args:
            utterance (str): Small piece of text outputted by the user
        """
        self.utterance_buffer += " " + utterance
        self.ten_env.log_debug(f"Updated utterance buffer: {self.utterance_buffer}")

    def flush_utterance_buffer(self) -> None:
        """
        Flush the utterance buffer on a conversation partner switch (when user stops talking and no backchannel detected) or when a backchannel was outputted
        """

        self.utterance_buffer = ""

    def get_backchannel_class(self, utterance: str) -> tuple[BackchannelType, float]:
        """
        Retrieve type of backchannel based on previous utterance

        Returns:
            BackchannelType: Type of backchannel, could be either ASSESSMENT or CONTINUER
        """

        encoding = self.tokenizer(
            utterance,
            truncation=True,
            padding=True,
            max_length=512,
            return_tensors="pt",
        )
        encoding = {k: v.to(self.device) for k, v in encoding.items()}

        with torch.no_grad():
            logits = self.model(**encoding).logits
            probs = torch.softmax(logits, dim=-1).squeeze(0)

        pred_idx = int(torch.argmax(probs).item())
        id2label = self.model.config.id2label or {}
        predicted_label = id2label.get(str(pred_idx), id2label.get(pred_idx, f"LABEL_{pred_idx}"))
        confidence = float(probs[pred_idx].item())

        return BackchannelType(predicted_label), confidence

    async def send_backchannel(self, type: BackchannelType, timestamp: int) -> None:
        """
        Send a backchannel audio frame to the next extension in line

        Args:
            type (BackchannelType): Exact backchannel type needed to decide which backchannel should be outputted.
        """
        backchannel_audio_files = {BackchannelType.ASSESSMENT: ["i_see", "sure"], BackchannelType.CONTINUER: ["go_on", "mmhm", "right", "uhhuh", "yeah"]}

        audio_file_dir = "ten_packages/extension/backchannel_generation_python/"

        backchannel_file = (
            audio_file_dir
            + random.choice(backchannel_audio_files[type])
            + ".wav"
        )

        with wave.open(backchannel_file, "rb") as audio:
            sample_rate = audio.getframerate()
            channels = audio.getnchannels()
            bytes_per_sample = audio.getsampwidth()
            raw_data = audio.readframes(audio.getnframes())

        frame_duration_ms = 10
        samples_per_frame = int(sample_rate * frame_duration_ms / 1000)
        bytes_per_frame = samples_per_frame * bytes_per_sample * channels

        if bytes_per_frame == 0:
            return

        total_frames = len(raw_data) // bytes_per_frame

        for frame_idx in range(total_frames):

            start_byte = frame_idx * bytes_per_frame
            end_byte = start_byte + bytes_per_frame
            frame_data = raw_data[start_byte:end_byte]

            # Create AudioFrame
            backchannel_frame = AudioFrame.create("pcm_frame")
            backchannel_frame.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
            backchannel_frame.set_bytes_per_sample(bytes_per_sample)
            backchannel_frame.set_sample_rate(sample_rate)
            backchannel_frame.set_number_of_channels(channels)
            backchannel_frame.set_samples_per_channel(samples_per_frame)
            backchannel_frame.set_timestamp(timestamp + frame_idx * frame_duration_ms * 1000)
            backchannel_frame.set_eof(False)

            # Fill with PCM data
            backchannel_frame.alloc_buf(len(frame_data))
            buf = backchannel_frame.lock_buf()
            buf[:] = frame_data
            backchannel_frame.unlock_buf(buf)

            # Send audio frame
            self.ten_env.log_debug(f"Sending backchannel audio frame {frame_idx + 1}/{total_frames}")
            await self.ten_env.send_audio_frame(backchannel_frame)

            # Wait for frame duration to enable real-time playback
            await asyncio.sleep(frame_duration_ms / 1000.0)

    async def process_frame(self, samples: bytearray, timestamp: int) -> None:

        if self.backchannel_opportunity and time.time_ns() // 1000 - self.time_since_bop > self.pause_req_ms and self.latest_bc_class is not None:
            self.last_bc_time = time.time_ns() // 1000
            self.flush_utterance_buffer()

            # Run backchannel sending in another thread to avoid blocking the main thread with sending
            self.send_backchannel_task = asyncio.create_task(
                self.send_backchannel(self.latest_bc_class, timestamp)
            )
            return

        pitch_condition_met = self.detect_pitch_variation(samples)

        if pitch_condition_met:

            self.ten_env.log_debug("Pitch variation detected! Now detecting silence")

            talking_time = self.get_latest_speech_time(time.time_ns() // 1000)

            time_since_bc = self.get_time_since_latest_bc(time.time_ns() // 1000)

            if talking_time >= self.speech_req_ms and time_since_bc >= self.bc_cooldown_ms:

                self.ten_env.log_debug("Backchannel opportunity! now waiting 400 ms")

                # Currently we are in a different state: backchannel opportunity -> which means that we need to wait 400ms
                # So we need to wait 400ms after pich fall or rising and then detect whether not in talking stage.
                # If not in talking stage we can output backchannel

                self.time_since_bop = time.time_ns() // 1000
                self.latest_bc_class, _ = await asyncio.to_thread(
                    self.get_backchannel_class,
                    self.utterance_buffer.strip(),
                ) # change to self.utterance_buffer

    async def stop(self) -> None:
        if self.send_backchannel_task is not None:
            self.send_backchannel_task.cancel()
            try:
                await self.send_backchannel_task
            except asyncio.CancelledError:
                pass
            self.send_backchannel_task = None
