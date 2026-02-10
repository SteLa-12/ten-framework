import atexit
import socket
import logging
import os
import time
import librosa

class PepperClient:
    def __init__(self, port: int = 5001, pepper_ip: str = "192.168.0.102", host_ip: str = "127.0.0.1"):
        """
        Initialize the PepperClient with the given port and Pepper IP address.

        Args:
            port (int): The port number for the socket connection. Default is 5001.
            pepper_ip (str): The IP address of the Pepper robot. Default is "192.168.0.102".
            host_ip (str): The IP address of the host machine. Default is "127.0.0.1".
        """

        self.pepper_ip = pepper_ip

        try:
            host = host_ip
            self.server_socket = socket.socket()
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((host, port))
            self.server_socket.listen(1)  # Enable server to accept connections
            print(f"PepperClient initialized. Listening on {host}:{port} for Pepper connection...")
            logging.info(f"Listening on {host}:{port}")

            # Blocking call - wait for Pepper to connect
            logging.info("Waiting for Pepper to connect...")
            self.client_socket, address = self.server_socket.accept()
            logging.info(f"Connected to Pepper at: {address}")

            # Set timeout for receiving messages to prevent indefinite blocking
            self.client_socket.settimeout(10.0)  # 10 second timeout

            # Register cleanup
            atexit.register(self.close_socket)

        except Exception as e:
            logging.error(f"Failed to establish connection with Pepper: {str(e)}")
            raise

    def send_message(self, message: str):
        """
        Send text message or command to Pepper
        Args:
            message (str): The message or command to send to Pepper.
        """
        try:
            self.client_socket.send(message.encode())
            logging.info(f"Sent to Pepper: {message}")
        except Exception as e:
            logging.error(f"Failed to send message to Pepper: {e}")

    def recv_message(self) -> str:
        """
        Receive message from Pepper with timeout handling

        Returns:
            str: The message received from Pepper, or "error" if an exception occurred.
        """
        try:
            message = self.client_socket.recv(1024 * 4).decode('utf-8')
            logging.info(f"Received from Pepper: {message}")
            return message
        except Exception as e:
            logging.error(f"Failed to receive message from Pepper: {e}")
            return "error"

    def send_and_wait_for_response(self, message: str) -> str:
        """
        Send message and wait for specific response from Pepper

        Args:
            message (str): The message or command to send to Pepper.

        Returns:
            str: The response received from Pepper.
        """
        logging.info(f"Sending message to Pepper and waiting for response: {message}")
        self.send_message(message)
        response = self.recv_message()

        return response

    def copy_path_to_pepper(self, file_number: int, audio_file_path: str = "pepper_response.mp3"):
        """
        Copy the specified audio file to the Pepper robot using scp command.
        """

        os.system(
            f'scp {audio_file_path} ' #path to the file
            f'nao@{self.pepper_ip}:/home/nao/pepper_response_{file_number}.mp3') #path to the pepper

    def audio_time_silence(self, audio_file_path: str) -> None:
        """
        Calculate the duration of the audio file and sleep for that duration to ensure Pepper has enough time to play the audio before proceeding with further commands or actions.

        Args:
            audio_file_path (str): The path to the audio file for which to calculate the duration and sleep.
        """
        audio_time = librosa.get_duration(path=audio_file_path)
        time.sleep(audio_time)

    def close_socket(self) -> None:
        try:
            self.client_socket.close()
        except:
            pass
