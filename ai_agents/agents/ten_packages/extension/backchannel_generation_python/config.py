from pydantic import BaseModel

class BackchannelConfig(BaseModel):
    """_summary_

    Args:
        pitch_fall_threshold_hz (_float_): threshold for pitch fall to trigger backchannel generation
        frame_rate (_int_): amount of frames per second
        chunk_size (_int_): amount of bytes per frame
        silence_threshold (_float_): value below which audio will be considered silent
        pause_req_ms (_int_): amount of speechless ms after pitch fall before backchannel opportunity
        speech_req_ms (_int_): amount of ms with speech before pitch fall or rising
        pitch_window_ms (_int_): amount of ms in which a pitch fall or rising is being considered
        bc_cooldown_ms (_int_): amount of ms till new output of backhannel
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