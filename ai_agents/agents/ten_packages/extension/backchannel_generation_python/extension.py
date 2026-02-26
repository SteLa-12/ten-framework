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
from .backchannel_detection import RealtimeBackchanneler
from .config import BackchannelConfig


class Extension(AsyncExtension):
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_init")

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_start")

        config_json, _ = await ten_env.get_property_to_json("")

        self.config = BackchannelConfig.model_validate_json(config_json)

        ten_env.log_info(
            f"pitch_fall_threshold_hz={self.config.pitch_fall_threshold_hz:.2f}"
        )

        self.last_pitch_hz: float | None = None
        self.backchannel_predictor = RealtimeBackchanneler(ten_env, self.config.frame_rate, self.config.chunk_size, self.config.silence_threshold, self.config.pause_req_ms, self.config.speech_req_ms, self.config.pitch_window_ms, self.config.pitch_shift_hz, self.config.bc_cooldown_ms)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_stop")

        # IMPLEMENT: clean up resources

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_deinit")

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log(LogLevel.DEBUG, "on_cmd name {}".format(cmd_name))

        # IMPLEMENT: process cmd

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

        self.backchannel_predictor.process_frame(audio_frame)

    async def on_video_frame(
        self, ten_env: AsyncTenEnv, video_frame: VideoFrame
    ) -> None:
        video_frame_name = video_frame.get_name()
        ten_env.log(LogLevel.DEBUG, "on_video_frame name {}".format(video_frame_name))

        # IMPLEMENT: process video frame
