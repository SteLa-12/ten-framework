#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import asyncio
import queue
import random
import wave
from pydub import AudioSegment

from ten_runtime import (
    AudioFrame,
    VideoFrame,
    AsyncTenEnv,
    AsyncExtension,
    Cmd,
    StatusCode,
    CmdResult,
    Data,
    LogLevel,
)
from ten_runtime.audio_frame import AudioFrameDataFmt
from .config import BCGenPythonConfig

from maai import Maai, MaaiInput


class BCGenPythonExtension(AsyncExtension):
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_init")
        await super().on_init(ten_env)

        self.ten_env = ten_env

        config_json, _ = await ten_env.get_property_to_json("")

        self.config = BCGenPythonConfig.model_validate_json(config_json)

        self.user_speaking: bool = False

        self.time_since_last_bc: int = 0

        self.backchannel_audio: list[str] = ["go_on.wav", "i_see.wav", "mmhm.wav", "right.wav", "sure.wav", "uhhuh.wav", "yeah.wav"]
        self.amount_of_backchannels: int = len(self.backchannel_audio)
        self.backchannel_dir: str = f"backchannel_audio_{self.config.voice}/"

        self.user_audio: MaaiInput.Chunk = MaaiInput.Chunk()
        self.system_audio: MaaiInput.Chunk = MaaiInput.Chunk()

        # Testing what maai is receiving as input to the model
        self.input_audio_buffer: bytes = b""
        self.buffer_count = 0

        ten_env.log_info("Initializing MaAI BC model...")

        self.maai = Maai(
            mode='bc',
            lang='en',
            frame_rate=5,
            context_len_sec=20,
            audio_ch1=self.user_audio,
            audio_ch2=self.system_audio,
            device="cpu",
        )

        ten_env.log_info("Starting MaAI BC model...")

        self.maai.start()

        ten_env.log_info("MaAI BC model initialized.")

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_start")

        # IMPLEMENT: read properties, initialize resources

        if not self.config:
            raise ValueError("Configuration not loaded properly.")

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_stop")

        # IMPLEMENT: clean up resources

        ten_env.log(LogLevel.INFO, "Stopping MaAI BC model...")

        self.maai.stop()

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_deinit")

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log(LogLevel.DEBUG, "on_cmd name {}".format(cmd_name))

        if cmd_name == "start_of_sentence":
            ten_env.log_info("[VAD]: User started speaking.")
            self.user_speaking = True

        if cmd_name == "end_of_sentence":
            ten_env.log_info("[VAD]: User stopped speaking.")
            self.user_speaking = False

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log(LogLevel.DEBUG, "on_data name {}".format(data_name))

        if data_name == "text_data":
            is_final = False
            try:
                is_final, _ = data.get_property_bool("is_final")
            except Exception as _e:
                pass
            if is_final:
                ten_env.log_info("[VAD]: User finished speaking.")
                self.user_speaking = False
            else:
                ten_env.log_info("[VAD]: User is speaking.")
                self.user_speaking = True

        # IMPLEMENT: process data

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        audio_frame_name = audio_frame.get_name()

        # IMPLEMENT: process audio frame

        # Retrieving audio PCM frame data
        input_frame_buf: bytearray = audio_frame.get_buf()
        # self.input_audio_buffer += input_frame_buf

        # # # Storing frames to .wav file for debugging
        # # TODO: remove in future
        # if self.buffer_count % 500 == 0:
        #     ten_env.log_info(f"Accumulated audio buffer size: {len(self.input_audio_buffer)} bytes")
        #     # write buffer to file for inspection
        #     with wave.open("bc_input_audio_buffer_" + str(self.buffer_count // 500) + ".wav", "wb") as f:
        #         f.setnchannels(audio_frame.get_number_of_channels())
        #         f.setframerate(audio_frame.get_sample_rate())
        #         f.setsampwidth(audio_frame.get_bytes_per_sample())
        #         f.writeframes(self.input_audio_buffer)
        #     self.input_audio_buffer = b""
        # self.buffer_count += 1

        # # Feed audio frame to MaAI input
        if self.user_speaking:
            self.user_audio.put_chunk(input_frame_buf)
        else:
            self.user_audio.put_chunk(b'\x00' * len(input_frame_buf))  # zero input

        self.system_audio.put_chunk(b'\x00' * len(input_frame_buf))  # zero input

        try:
            result = self.maai.result_dict_queue.get_nowait()
            ten_env.log_debug("MaAI BC result: {}".format(result['p_bc']))
            self.time_since_last_bc += 1
            if result['p_bc'] >= self.config.threshold and self.time_since_last_bc >= self.config.holdback and self.user_speaking == True:
                ten_env.log(LogLevel.INFO, "Backchannel reaction detected! With probability: {:.2f}".format(result['p_bc']))

                self.time_since_last_bc = 0

                # Start audio playback asynchronously
                asyncio.create_task(self.send_backchannel_audio(ten_env))

        except queue.Empty:
            return

    async def on_video_frame(
        self, ten_env: AsyncTenEnv, video_frame: VideoFrame
    ) -> None:
        video_frame_name = video_frame.get_name()
        ten_env.log(LogLevel.DEBUG, "on_video_frame name {}".format(video_frame_name))

        # IMPLEMENT: process video frame

    async def send_backchannel_audio(
        self, ten_env: AsyncTenEnv
    ) -> None:

        # First load audio file into aduiosegment

        audio_file = self.backchannel_dir + self.backchannel_audio[
            random.randint(0, self.amount_of_backchannels - 1)
        ]

        audio: AudioSegment = AudioSegment.from_file(audio_file)

        if audio is None:
            ten_env.log(LogLevel.ERROR, "Backchannel audio file not found or could not be opened.")
            return

        audio = audio.set_frame_rate(16000).set_channels(1)

        sample_rate = 16000
        bytes_per_sample = 2  # 16-bit PCM
        channels = 1
        frame_duration_ms = 10
        samples_per_frame = int(
            sample_rate * frame_duration_ms / 1000
        )  # 160 samples
        bytes_per_frame = (
            samples_per_frame * bytes_per_sample * channels
        )  # 320 bytes

        raw_data = audio.raw_data
        if raw_data is None:
            ten_env.log(LogLevel.ERROR, "Failed to read backchannel audio file.")
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
            backchannel_frame.set_timestamp(frame_idx * frame_duration_ms * 1000)
            backchannel_frame.set_eof(False)

            # Fill with PCM data
            backchannel_frame.alloc_buf(len(frame_data))
            buf = backchannel_frame.lock_buf()
            buf[:] = frame_data
            backchannel_frame.unlock_buf(buf)

            # Send audio frame
            ten_env.log(LogLevel.DEBUG, f"Sending backchannel audio frame {frame_idx + 1}/{total_frames}")
            await ten_env.send_audio_frame(backchannel_frame)

            # Wait for frame duration to enable real-time playback
            await asyncio.sleep(frame_duration_ms / 1000.0)
