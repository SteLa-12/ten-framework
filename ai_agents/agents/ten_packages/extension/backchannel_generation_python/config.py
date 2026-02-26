from pydantic import BaseModel

class BackchannelConfig(BaseModel):
    """_summary_

    Args:
        pitch_fall_threshold_hz (_float_): threshold for pitch fall to trigger backchannel generation
    """
    pitch_fall_threshold_hz: float = 30.0
    frame_rate: int = 16000
    chunk_size: int = 160
    silence_threshold: float = 0.015
    pause_req_ms: int = 400
    speech_req_ms: int = 1000
    pitch_window_ms: int = 100
    pitch_shift_hz: float = 30.0
    bc_cooldown_ms: int = 1400