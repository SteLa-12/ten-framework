import numpy as np
import aubio
import time
from collections import deque

from ten_runtime.async_ten_env import AsyncTenEnv
from ten_runtime.audio_frame import AudioFrame

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
        self.is_speaking = False
        self.speech_start_time = 0.0
        self.silence_start_time = 0.0
        self.last_bc_time = 0.0

        # Calculate how many chunks fit into 100ms (100ms / 32ms ≈ 3 chunks)
        buffer_len = max(1, int((self.pitch_window_ms / 1000.0) / (self.chunk_size / self.frame_rate)))
        self.pitch_buffer = deque(maxlen=buffer_len)

        # Latched states at the moment speech ends
        self.pitch_valid_at_speech_end = False
        self.speech_duration_at_end = 0.0

    def process_frame(self, audio_frame: AudioFrame):
        now = time.time()

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

        self.ten_env.log_debug(f"RMS: {rms:.4f}")

        # Calculate Pitch
        pitch = self.pitch_detector(samples_np)[0]
        if pitch > 0: # 0 means unvoiced/no pitch detected
            self.pitch_buffer.append(pitch)

        # Continuously evaluate if the current rolling 100ms window has a 30Hz drop/rise (P3 & P4)
        current_pitch_shift = 0.0
        if len(self.pitch_buffer) > 1:
            current_pitch_shift = max(self.pitch_buffer) - min(self.pitch_buffer)

        # Check if a pitch rising or fall is detected in the current window
        pitch_condition_met = current_pitch_shift >= self.pitch_shift_hz

        if pitch_condition_met:
            self.ten_env.log_debug(f"Pitch condition met! Shift: {current_pitch_shift:.2f} Hz")

            self.ten_env.log_debug(f"RMS = {rms:.4f}, Speech Duration at End = {self.speech_duration_at_end:.2f} ms, Cooldown = {(now - self.last_bc_time)*1000:.2f} ms")

        # Detect whether we are currently in speech or silence and update states accordingly
        if rms > self.silence_threshold:
            # STATE: SPEECH
            if not self.is_speaking:
                self.is_speaking = True
                self.speech_start_time = now

            # Keep updating our "end of speech" variables as long as they are talking
            self.pitch_valid_at_speech_end = pitch_condition_met
            self.speech_duration_at_end = (now - self.speech_start_time) * 1000

        else:
            # STATE: SILENCE
            if self.is_speaking:
                self.is_speaking = False
                self.silence_start_time = now
                self.pitch_buffer.clear() # Clear buffer so we don't bleed old pitches into next turn

            # Calculate durations in milliseconds
            pause_duration_ms = (now - self.silence_start_time) * 1000
            cooldown_ms = (now - self.last_bc_time) * 1000

            # --- Check all BC Triggers ---
            p1 = pause_duration_ms >= self.pause_req_ms
            p2 = self.speech_duration_at_end >= self.speech_req_ms
            p3_p4 = self.pitch_valid_at_speech_end
            p5 = cooldown_ms >= self.bc_cooldown_ms

            if p1 and p2 and p3_p4 and p5:
                self.ten_env.log_info(f"[{time.strftime('%X')}] BC OUTPUT DETECTED! --> (Hmm / Yeah)")

                # Update last BC time (P5)
                self.last_bc_time = now

                # Reset the pitch latch to prevent repeating BCs during the same long pause
                self.pitch_valid_at_speech_end = False