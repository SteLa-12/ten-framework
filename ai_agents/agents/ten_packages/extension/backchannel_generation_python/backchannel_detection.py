import numpy as np
from aubio import pitch
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
        ) -> None:
        """
        Backchannel processor: listen to audio frames and find backchannel opportunities,
        generate backchannel frames and output to next extension

        Args:
            ten_env (AsyncTenEnv): Asynchronous Ten Environment
            frame_rate (int, optional): Rate of the frames send to the backchannel extension. Defaults to 16000.
            chunk_size (int, optional): Size of the frames. Defaults to 160.
            silence_threshold (float, optional): Threshold of MSE at which the frame is considered silent. Defaults to 0.015.
            pause_req_ms (int, optional): Duration of silence after a pitch rising. Defaults to 400.
            speech_req_ms (int, optional): Duration of speech required before pitch fall or rising. Defaults to 1000.
            pitch_window_ms (int, optional): Frame duration in which pitch falls and risings are considered. Defaults to 100.
            pitch_shift_hz (float, optional): Amount of shift in the pitch. Defaults to 30.0.
            bc_cooldown_ms (int, optional): Minimal duration between subsequent backchannels. Defaults to 1400.

        Raises:
            FileNotFoundError: If model path is not found for backchannel prediction
        """

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
        self.speaking_change: bool = False

        # Calculate how many chunks fit into 100ms (100ms / 32ms ≈ 3 chunks)
        buffer_len = max(1, int((self.pitch_window_ms / 1000.0) / (self.chunk_size / self.frame_rate)))
        self.pitch_buffer = deque(maxlen=buffer_len)

        # Latched states at the moment speech ends
        self.pitch_valid_at_speech_end = False
        self.speech_duration_at_end = 0.0

        # Utterance buffer which gets filled as soon as results from the ASR module are available
        self.utterance_buffer: str = ""
        self.backchannel_frames: list[AudioFrame] = []

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
        self.classify_task: asyncio.Task | None = None

    def _predict_backchannel_label_sync(self, utterance: str) -> tuple[str, np.ndarray]:
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
        predicted_label = id2label.get(
            str(pred_idx), id2label.get(pred_idx, f"LABEL_{pred_idx}")
        )
        return predicted_label, probs.cpu().numpy()

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

    def set_talking(self) -> None:
        """
        Set current state to talking

        Args:
            current_time (int): Time at which function call is invoked
        """
        self.is_speaking = True
        self.speaking_change = True

    def set_silence(self) -> None:
        """
        Set current state to silent

        Args:
            current_time (int): Time at which function call is invoked
        """
        self.is_speaking = False
        self.speaking_change = True
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
        self.utterance_buffer = utterance
        self.ten_env.log_debug(f"Updated utterance buffer: {self.utterance_buffer}")

    def flush_utterance_buffer(self) -> None:
        """
        Flush the utterance buffer on a conversation partner switch (when user stops talking and no backchannel detected) or when a backchannel was outputted
        """

        self.utterance_buffer = ""

    async def get_backchannel_class(self, utterance: str, timestamp: int) -> None:
        """
        Retrieve type of backchannel based on previous utterance

        Returns:
            BackchannelType: Type of backchannel, could be either ASSESSMENT or CONTINUER
        """

        self.ten_env.log_debug(f"Predicting backchannel class for utterance: '{utterance}' with current buffer: '{self.utterance_buffer}'")

        predicted_label, probs = await asyncio.to_thread(
            self._predict_backchannel_label_sync, utterance
        )

        self.ten_env.log_debug(
            f"Predicted backchannel class: {predicted_label} with probabilities {probs} for utterance: '{utterance}'"
        )

        self.latest_bc_class = BackchannelType(predicted_label)

        # Immediately generate frames that can be sent when pause conditions are met.
        await self.create_backchannel(self.latest_bc_class, timestamp)

    async def create_backchannel(self, type: BackchannelType, timestamp: int) -> None:
        """
        Send a backchannel audio frame to the next extension in line

        Args:
            type (BackchannelType): Exact backchannel type needed to decide which backchannel should be outputted.
        """
        backchannel_audio_files = {BackchannelType.ASSESSMENT: ["ga_verder", "ik_snap_het", "inderdaad", "juist", "precies"], BackchannelType.CONTINUER: ["ja", "mm_hm", "oke", "uh_huh", "zeker"]}

        audio_file_dir = "ten_packages/extension/backchannel_generation_python/backchannel_audio_male/"

        backchannel_file = (
            audio_file_dir
            + random.choice(backchannel_audio_files[type])
            + ".wav"
        )

        self.backchannel_frames.clear()

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
            backchannel_frame.set_timestamp(timestamp + frame_idx * frame_duration_ms)
            backchannel_frame.set_eof(False)

            # Fill with PCM data
            backchannel_frame.alloc_buf(len(frame_data))
            buf = backchannel_frame.lock_buf()
            buf[:] = frame_data
            backchannel_frame.unlock_buf(buf)

            self.backchannel_frames.append(backchannel_frame)

        self.ten_env.log_debug(f"Created {len(self.backchannel_frames)} frames for backchannel type {type} with utterance '{self.utterance_buffer}'")

    async def send_backchannel(self) -> None:
        """
        Send the backchannel frames to the next extension in the graph
        """

        if not self.backchannel_frames:
            return
        for backchannel_frame in self.backchannel_frames:
            await self.ten_env.send_audio_frame(backchannel_frame)
        self.backchannel_frames.clear()

    async def process_frame(self, samples: bytearray, timestamp: int) -> None:
        """
        Process a specific audio frame and detect whether a backchannel should be outputted or not

        Args:
            samples (bytearray): The exact data of the current audio frame which should be processed
            timestamp (int): time in ms at which the audio frame is in the current conversation
        """

        if not self.is_speaking:
            return

        if self.is_speaking and self.speaking_change:
            self.speech_start_time = timestamp
        elif self.speaking_change:
            self.silence_start_time = timestamp
        self.speaking_change = False

        if self.backchannel_opportunity and timestamp - self.time_since_bop > self.pause_req_ms and self.latest_bc_class is not None:
            self.last_bc_time = timestamp

            self.ten_env.log_info(f"[Backchannel opportunity] Outputting backchannel of type {self.latest_bc_class} with utterance buffer: '{self.utterance_buffer}'")

            self.flush_utterance_buffer()

            # Create new task for backchannel audio outputting
            self.send_backchannel_task = asyncio.create_task(
                self.send_backchannel()
            )

            # Set backchannel opportunity to false and reset latest bc class to avoid multiple backchannels in a row without new pitch variation or new utterance
            self.backchannel_opportunity = False
            self.latest_bc_class = None

            return

        pitch_condition_met = self.detect_pitch_variation(samples)

        if pitch_condition_met:

            self.ten_env.log_debug("Pitch variation detected! Now detecting silence")

            talking_time = self.get_latest_speech_time(timestamp)

            time_since_bc = self.get_time_since_latest_bc(timestamp)

            if talking_time >= self.speech_req_ms and time_since_bc >= self.bc_cooldown_ms:

                self.ten_env.log_debug("[Backchannel opportunity] now waiting 400 ms")

                # Currently we are in a different state: backchannel opportunity -> which means that we need to wait 400ms
                # So we need to wait 400ms after pich fall or rising and then detect whether not in talking stage.
                # If not in talking stage we can output backchannel

                self.backchannel_opportunity = True

                self.time_since_bop = timestamp
                if self.classify_task is None or self.classify_task.done():
                    self.classify_task = asyncio.create_task(
                        self.get_backchannel_class(
                            self.utterance_buffer.strip(),
                            timestamp + 400,
                        )
                    )

    async def stop(self) -> None:
        if self.classify_task is not None:
            self.classify_task.cancel()
            try:
                await self.classify_task
            except asyncio.CancelledError:
                pass
            self.classify_task = None

        if self.send_backchannel_task is not None:
            self.send_backchannel_task.cancel()
            try:
                await self.send_backchannel_task
            except asyncio.CancelledError:
                pass
            self.send_backchannel_task = None
