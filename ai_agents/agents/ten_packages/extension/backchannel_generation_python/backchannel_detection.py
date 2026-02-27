import numpy as np
import aubio
import time
from collections import deque
import enum

from ten_runtime.async_ten_env import AsyncTenEnv
from ten_runtime.audio_frame import AudioFrame

class BackchannelType(enum.Enum):
    ASSESSMENT = 1
    CONTINUER = 2

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
        self.pitch_detector = aubio.pitch("yin", 2048, chunk_size, frame_rate)
        self.pitch_detector.set_unit("Hz")
        self.pitch_detector.set_silence(-40)

        # State Tracking
        self.is_speaking: bool = False
        self.speech_start_time: int = 0
        self.silence_start_time: int = 0
        self.last_bc_time: int = 0

        # Calculate how many chunks fit into 100ms (100ms / 32ms ≈ 3 chunks)
        buffer_len = max(1, int((self.pitch_window_ms / 1000.0) / (self.chunk_size / self.frame_rate)))
        self.pitch_buffer = deque(maxlen=buffer_len)

        # Latched states at the moment speech ends
        self.pitch_valid_at_speech_end = False
        self.speech_duration_at_end = 0.0

    def detect_pitch_variation(self, samples: bytearray) -> bool:
        """
        Detect wheter there is a pitch variation which is larger than the predefined threshold

        Args:
            audio_frame (AudioFrame): Current processed Audio Frame

        Returns:
            bool: True when a pitch rising or fall is detected which is higher than {self.pitch_shift_hz}
        """

        samples = np.frombuffer(samples, dtype= np.int16).astype(np.float32)

        pitch = self.pitch_detector(samples)[0]

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

    def get_backchannel_class(self) -> BackchannelType:
        """
        Retrieve type of backchannel based on previous utterance

        Returns:
            BackchannelType: Type of backchannel, could be either ASSESSMENT or CONTINUER
        """

    def process_frame(self, audio_frame: AudioFrame):

        samples = audio_frame.get_buf()
        if not samples:
            return

        bit_depth = audio_frame.get_bytes_per_sample() * 8
        n_channels = audio_frame.get_number_of_channels()

        bits_per_sample = bit_depth // n_channels

        sample_map = {8: np.int8, 16: np.int16, 24: np.int32, 32: np.int32}

        samples_np = np.frombuffer(samples, dtype=sample_map[bits_per_sample]).astype(np.float32)

        # Calculate Volume (RMS)
        rms = float(np.sqrt(np.mean(samples_np ** 2)))

        pitch_condition_met = self.detect_pitch_variation(samples)

        if pitch_condition_met:

            self.ten_env.log_debug(f"Pitch variation detected! Now detecting silence")

            talking_time = self.get_latest_speech_time(time.time_ns() // 1000)

            time_since_bc = self.get_time_since_latest_bc(time.time_ns() // 1000)

            if talking_time >= self.speech_req_ms and time_since_bc >= self.bc_cooldown_ms:

                self.ten_env.log_debug(f"Backchannel opportunity! now waiting 400 ms")

                # Currently we are in a different state: backchannel opportunity -> which means that we need to wait 400ms
                # So we need to wait 400ms after pich fall or rising and then detect whether not in talking stage.
                # If not in talking stage we can output backchannel
