import numpy as np
import aubio
import time
from collections import deque

# --- Algorithm Parameters ---
RATE = 16000
CHUNK = 160  # 32ms frames for low latency
SILENCE_THRESHOLD = 0.015  # Amplitude threshold (TUNE THIS for your mic!)

# P-Conditions
PAUSE_REQ_MS = 400         # P1
SPEECH_REQ_MS = 1000       # P2
PITCH_WINDOW_MS = 100      # P3
PITCH_SHIFT_HZ = 30.0      # P4
BC_COOLDOWN_MS = 1400      # P5

class RealtimeBackchanneler:
    def __init__(self, ten_env):

        self.ten_env = ten_env

        # Initialize Real-time Pitch Tracker
        self.pitch_detector = aubio.pitch("yin", 2048, CHUNK, RATE)
        self.pitch_detector.set_unit("Hz")
        self.pitch_detector.set_silence(-40)

        # State Tracking
        self.is_speaking = False
        self.speech_start_time = 0.0
        self.silence_start_time = 0.0
        self.last_bc_time = 0.0

        # Calculate how many chunks fit into 100ms (100ms / 32ms ≈ 3 chunks)
        buffer_len = max(1, int((PITCH_WINDOW_MS / 1000.0) / (CHUNK / RATE)))
        self.pitch_buffer = deque(maxlen=buffer_len)

        # Latched states at the moment speech ends
        self.pitch_valid_at_speech_end = False
        self.speech_duration_at_end = 0.0

    def process_frame(self, samples):
        now = time.time()

        # Normalize input frame to float32 in [-1, 1] for both RMS and pitch tracking.
        if isinstance(samples, (bytes, bytearray, memoryview)):
            samples_np = np.frombuffer(samples, dtype=np.int16).astype(np.float32)
            if samples_np.size == 0:
                return
            samples_np /= 32768.0
        else:
            samples_np = np.asarray(samples, dtype=np.float32)
            if samples_np.size == 0:
                return

            # If integer PCM is provided as an ndarray/list, normalize to [-1, 1].
            if np.max(np.abs(samples_np)) > 1.0:
                samples_np /= 32768.0

        # Calculate Volume (RMS)
        rms = float(np.sqrt(np.mean(samples_np * samples_np)))

        # Calculate Pitch
        pitch = self.pitch_detector(samples_np)[0]
        if pitch > 0: # 0 means unvoiced/no pitch detected
            self.pitch_buffer.append(pitch)

        # Continuously evaluate if the current rolling 100ms window has a 30Hz drop/rise (P3 & P4)
        current_pitch_shift = 0.0
        if len(self.pitch_buffer) > 1:
            current_pitch_shift = max(self.pitch_buffer) - min(self.pitch_buffer)

        # Check if a pitch rising or fall is detected in the current window
        pitch_condition_met = current_pitch_shift >= PITCH_SHIFT_HZ

        # Detect whether we are currently in speech or silence and update states accordingly
        if rms > SILENCE_THRESHOLD:
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
            p1 = pause_duration_ms >= PAUSE_REQ_MS
            p2 = self.speech_duration_at_end >= SPEECH_REQ_MS
            p3_p4 = self.pitch_valid_at_speech_end
            p5 = cooldown_ms >= BC_COOLDOWN_MS

            if p1 and p2 and p3_p4 and p5:
                self.ten_env.log_info(f"[{time.strftime('%X')}] BC OUTPUT DETECTED! --> (Hmm / Yeah)")

                # Update last BC time (P5)
                self.last_bc_time = now

                # Reset the pitch latch to prevent repeating BCs during the same long pause
                self.pitch_valid_at_speech_end = False