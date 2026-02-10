from pydantic import BaseModel

class PepperConfig(BaseModel):
    """Configuration for the Pepper robot connection.

    Args:
        host_ip_address (str): The IP address of the host machine.
        host_port (int): The port number for the host machine.
        pepper_ip_address (str): The IP address of the Pepper robot.
        pepper_port (int): The port number for the Pepper robot.
        face_size (float): The size of the face to track.
    """
    host_ip_address: str = "127.0.0.1"
    host_port: int = 5001
    pepper_ip_address: str = "192.168.0.127"
    pepper_port: int = 9559
    face_size: float = 0.1