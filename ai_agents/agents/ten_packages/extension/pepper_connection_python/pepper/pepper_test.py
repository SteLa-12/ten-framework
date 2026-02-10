"""
Test file for the pepper connection extension.
"""


# Example usage of the PepperClient
import sys
from pepper_client import PepperClient
from pepper_runner import init_pepper

import threading
import time
import logging

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

    pepper_ip = "192.168.0.127"  # Replace with your Pepper robot's IP address

    # Start the Pepper runner in a separate thread or process

    runner_thread = threading.Thread(target=init_pepper, args=(pepper_ip,))
    runner_thread.start()

    time.sleep(5)  # Wait for the Pepper runner to initialize and be ready to accept connections

    # Create a PepperClient instance to communicate with the Pepper runner
    client = PepperClient(pepper_ip=pepper_ip)
    # Example: Send a command to Pepper and wait for the response
    client.send_message("_stop_listening")

    time.sleep(2)  # Wait for a moment before sending the next command

    client.copy_path_to_pepper(0)
    response = client.send_message("_sending0")
    client.audio_time_silence("pepper_response.mp3")
    if response == "reproducing":
        print("Pepper is reproducing the audio file.")
    else:
        print(f"Unexpected response from Pepper: {response}")

    response = client.send_and_wait_for_response("_end_sequence")
    print(f"Response from Pepper: {response}")

    time.sleep(2)  # Wait for a moment before sending the next command

    response = client.send_and_wait_for_response("_final")
    print(f"Response from Pepper: {response}")

    time.sleep(2)  # Wait for a moment before ending the test
    print("Test completed. Closing connection.")

    runner_thread.join()  # Wait for the Pepper runner thread to finish

    print("Pepper runner thread has finished. Exiting test.")

    client.close_socket()  # Ensure the client socket is closed after the test

    print("Client socket closed. Exiting program.")

    sys.exit(0)