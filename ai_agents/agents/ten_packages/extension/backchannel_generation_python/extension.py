#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#

import asyncio

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
from .backchannel_detection import RealtimeBackchanneler
from .backchannel_processor import BackchannelProcessor
from .config import BackchannelConfig
import time


class Extension(AsyncExtension):
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_init")

        config_json, _ = await ten_env.get_property_to_json("")

        self.config = BackchannelConfig.model_validate_json(config_json)

        ten_env.log_info(
            f"pitch_fall_threshold_hz={self.config.pitch_fall_threshold_hz:.2f}"
        )

        self.last_pitch_hz: float | None = None
        self.main_runtime_task: asyncio.Task | None = None
        self.backchannel_predictor = RealtimeBackchanneler(ten_env, self.config.frame_rate, self.config.chunk_size, self.config.silence_threshold, self.config.pause_req_ms, self.config.speech_req_ms, self.config.pitch_window_ms, self.config.pitch_shift_hz, self.config.bc_cooldown_ms)
        self.backchannel_processor = BackchannelProcessor(self.backchannel_predictor, ten_env)

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_start")

        self.backchannel_processor.finish_event.clear()

        self.main_runtime_task = asyncio.create_task(self.backchannel_processor.run())


    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_stop")

        await self.backchannel_processor.stop()
        await self.backchannel_predictor.stop()

        if self.main_runtime_task is not None:
            self.main_runtime_task.cancel()
            try:
                await self.main_runtime_task
            except asyncio.CancelledError:
                pass
            self.main_runtime_task = None

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_deinit")

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log(LogLevel.DEBUG, "on_cmd name {}".format(cmd_name))

        # IMPLEMENT: process cmd

        if cmd_name == "start_of_sentence":
            # User started talking
            self.backchannel_predictor.set_talking(time.time_ns() // 1000)

        if cmd_name == "end_of_sentence":
            # User stopped talking
            self.backchannel_predictor.set_silence(time.time_ns() // 1000)

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

        bytes_per_sample = audio_frame.get_bytes_per_sample()
        if bytes_per_sample != 2:
            ten_env.log_debug(
                f"skip pitch detection: unsupported bytes_per_sample={bytes_per_sample}"
            )
            return

        await self.backchannel_processor.add_audio(audio_frame)

    async def on_video_frame(
        self, ten_env: AsyncTenEnv, video_frame: VideoFrame
    ) -> None:
        video_frame_name = video_frame.get_name()
        ten_env.log(LogLevel.DEBUG, "on_video_frame name {}".format(video_frame_name))

        # IMPLEMENT: process video frame
