from pydantic import BaseModel

class BCGenPythonConfig(BaseModel):
    """_summary_

    Args:
        device (_str_): whether to use 'cpu' or 'gpu' for model inference
        threshold (_float_): threshold for backchannel generation
    """
    device: str = "cpu" 
    threshold: float = 0.30
    holdback: int = 5
    voice: str = "male"
    if voice != "male" or voice != "female":
        voice = "male"