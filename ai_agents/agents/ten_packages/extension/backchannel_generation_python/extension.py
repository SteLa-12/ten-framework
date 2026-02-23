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


class Extension(AsyncExtension):
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_init")

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log(LogLevel.DEBUG, "on_start")

        self.pitch_fall_threshold_hz = 30.0
        self.last_pitch_hz: float | None = None
        self.backchannel_predictor = RealtimeBackchanneler(ten_env)

        try:
            threshold_result = await ten_env.get_property_float(
                "pitch_fall_threshold_hz"
            )
            if isinstance(threshold_result, tuple):
                threshold_value, threshold_error = threshold_result
                if threshold_error is None and threshold_value is not None:
                    self.pitch_fall_threshold_hz = float(threshold_value)
            elif threshold_result is not None:
                self.pitch_fall_threshold_hz = float(threshold_result)
        except Exception:
            ten_env.log_warn(
                "pitch_fall_threshold_hz not found or invalid, using default 30.0Hz"
            )

        ten_env.log_info(
            f"pitch_fall_threshold_hz={self.pitch_fall_threshold_hz:.2f}"
        )

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

        audio_frame_buffer = audio_frame.get_buf()
        if not audio_frame_buffer:
            return

        bytes_per_sample = audio_frame.get_bytes_per_sample()
        if bytes_per_sample != 2:
            ten_env.log_debug(
                f"skip pitch detection: unsupported bytes_per_sample={bytes_per_sample}"
            )
            return

        self.backchannel_predictor.process_frame(audio_frame_buffer)

    async def on_video_frame(
        self, ten_env: AsyncTenEnv, video_frame: VideoFrame
    ) -> None:
        video_frame_name = video_frame.get_name()
        ten_env.log(LogLevel.DEBUG, "on_video_frame name {}".format(video_frame_name))

        # IMPLEMENT: process video frame
