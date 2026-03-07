import asyncio
from ten_runtime.async_ten_env import AsyncTenEnv
from ten_runtime.audio_frame import AudioFrame
from .backchannel_detection import RealtimeBackchanneler


class BackchannelProcessor:
    def __init__(self, backchannel_detector: RealtimeBackchanneler, ten_env: AsyncTenEnv) -> None:
        self.backchannel_detector = backchannel_detector
        self.ten_env = ten_env
        self.audio_buffer = asyncio.Queue[AudioFrame | None]()
        self.finish_event = asyncio.Event()

        self.finish_event.clear()

    async def run(self) -> None:
        """
        Process the audio frames in the buffer and generate backchannel responses.
        """
        while not self.finish_event.is_set():
            audio_chunk = await self.audio_buffer.get()
            if audio_chunk is None:
                continue

            samples = audio_chunk.get_buf()
            await self.backchannel_detector.process_frame(
                samples, audio_chunk.get_timestamp()
            )

    async def add_audio(self, audio_chunk: AudioFrame) -> None:
        """
        Add an audio frame to the buffer

        Args:
            audio_chunk (AudioFrame): The audio frame to be added to the buffer.
        """
        await self.audio_buffer.put(audio_chunk)

    async def clear_buffer(self) -> None:
        """
        Clear the full buffer
        """
        while not self.audio_buffer.empty():
            self.audio_buffer.get_nowait()

    async def stop(self) -> None:
        """
        Stop the backchannel processor and clean up resources.
        """
        self.finish_event.set()
        await self.audio_buffer.put(None)
        await self.clear_buffer()
