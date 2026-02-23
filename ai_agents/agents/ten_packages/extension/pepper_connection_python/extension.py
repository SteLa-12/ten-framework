#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_runtime import (
    AudioFrame,
    VideoFrame,
    AsyncExtension,
    AsyncTenEnv,
    Cmd,
    StatusCode,
    CmdResult,
    Data,
    LogLevel,
)

from .pepper.pepper_client import PepperClient
from .pepper.pepper_runner import init_pepper
from .config import PepperConfig
import threading
import time
from pydub import AudioSegment

class Extension(AsyncExtension):
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_init")
        await super().on_init(ten_env)

        self.ten_env = ten_env

        config_json, _ = await ten_env.get_property_to_json("")

        self.config = PepperConfig.model_validate_json(config_json)

        self.runner_thread = threading.Thread(target=init_pepper, args=(self.config.pepper_ip_address, self.config.pepper_port, self.config.face_size, self.config.host_ip_address, self.config.host_port), daemon=True)
        self.runner_thread.start()

        time.sleep(1) # Wait for the Pepper runner to initialize and be ready to accept connections

        self.pepper_client = PepperClient(host_port=self.config.host_port, pepper_ip_address=self.config.pepper_ip_address, host_ip_address=self.config.host_ip_address)

        self.audio_buffer: bytearray = bytearray()

        self.speaking = False

        self.buffer_length = 100

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_start")

        # IMPLEMENT: read properties, initialize resources

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_stop")

        # IMPLEMENT: clean up resources

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_deinit")

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log(LogLevel.DEBUG, "on_cmd name {}".format(cmd_name))

        # IMPLEMENT: process cmd

        if cmd_name == "end_of_sentence":
            self.speaking = False
            # Send buffer to Pepper for playback and clear buffer
            await self._on_end_of_sequence(ten_env)

        if cmd_name == "start_of_sentence":
            self.speaking = True

        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log(LogLevel.DEBUG, "on_data name {}".format(data_name))

        # IMPLEMENT: process data

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        audio_frame_name = audio_frame.get_name()
        ten_env.log(LogLevel.DEBUG, "on_audio_frame name {}".format(audio_frame_name))

        # IMPLEMENT: process audio frame

        if self.speaking:
            audio_frame_buffer = audio_frame.get_buf()
            self.audio_buffer.extend(audio_frame_buffer)

        if len(self.audio_buffer) > self.buffer_length * 16000 * 2:  # Assuming 16kHz sample rate and 16-bit audio (2 bytes per sample)
            await self._on_end_of_sequence(ten_env)
            self.audio_buffer.clear()  # Clear the buffer after sending to Pepper

    async def on_video_frame(
        self, ten_env: AsyncTenEnv, video_frame: VideoFrame
    ) -> None:
        video_frame_name = video_frame.get_name()
        ten_env.log(LogLevel.DEBUG, "on_video_frame name {}".format(video_frame_name))

        # IMPLEMENT: process video frame

    async def _on_end_of_sequence(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "_on_end_of_sequence")

        # IMPLEMENT: process end of sequence event
        # At this point the extension should combine all audio fragments in the buffer and send audio file to Pepper for playback
        audio_file_path = "pepper_response.mp3"

        # Convert raw PCM audio buffer to MP3
        audio_segment = AudioSegment(
            data=self.audio_buffer,
            sample_width=2,  # 16-bit audio = 2 bytes per sample
            frame_rate=16000,  # 16kHz sample rate
            channels=1  # Mono audio
        )
        audio_segment.export(audio_file_path, format="mp3")

        self.pepper_client.copy_path_to_pepper(0, audio_file_path)
        response = self.pepper_client.send_message("_sending0")
        self.pepper_client.audio_time_silence(audio_file_path)
        if response == "reproducing":
            ten_env.log(LogLevel.INFO, "Pepper is reproducing the audio file.")
        else:
            ten_env.log(LogLevel.WARN, f"Unexpected response from Pepper: {response}")

        response = self.pepper_client.send_and_wait_for_response("_end_sequence")
        ten_env.log(LogLevel.INFO, f"Response from Pepper: {response}")

        self.audio_buffer.clear()  # Clear the buffer for the next sequence
