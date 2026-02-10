"""
Pepper Robot Runner

Local runner for the Pepper robot. This module interacts with the main functionalities of the Pepper robot, such as speech, motion, and tablet display. It establishes a socket connection to receive commands and data from an external source (e.g., a server or another application) and processes them accordingly.
"""

import socket
import qi
import sys
import threading
import time
import logging

class PepperRunner(object):
    def __init__(self, app: qi._Application, faceSize: float, host_ip: str = "127.0.0.1", port_number: int = 5001):
        """
        Initialize the PepperRunner with the given application and face size.

        Args:
            app (qi._Application): The Qi application instance.
            faceSize (float): The size of the face to track.
            host_ip (str): The IP address of the host machine. Default is "127.0.0.1".
            port_number (int): The port number for the socket connection. Default is 5001.
        """
        super(PepperRunner, self).__init__()

        self.host_ip = host_ip
        self.port_number = port_number

        app.start()
        # Session handling the running services on the robot
        session = app.session

        # Get services
        self.player = session.service("ALAudioPlayer")
        self.audio_device = session.service("ALAudioDevice")
        self.aup = session.service("ALAnimatedSpeech")
        self.animation_player_service = session.service("ALAnimationPlayer")
        self.motion_service = session.service("ALMotion")
        self.tracker_service = session.service("ALTracker")
        # self.tablet_service = session.service("ALTabletService")
        self.leds = session.service("ALLeds")
        self.posture_service = session.service("ALRobotPosture")

        # Wake up the robot and start tracking
        self.motion_service.wakeUp()
        self.posture_service.goToPosture("StandInit", 0.5)
        self.motion_service.setAngles("Head", [0.0, 0.0], 0.6)
        # Create led groups
        self.leds.createGroup("Eyes", ['RightFaceLed1', 'RightFaceLed2', 'RightFaceLed3',
                                       'RightFaceLed4', 'RightFaceLed5', 'RightFaceLed6',
                                       'RightFaceLed7', 'RightFaceLed8',
                                       'LeftFaceLed1', 'LeftFaceLed2', 'LeftFaceLed3',
                                       'LeftFaceLed4', 'LeftFaceLed5', 'LeftFaceLed6',
                                       'LeftFaceLed7', 'LeftFaceLed8'])

        self.leds.createGroup("CornerEyes", ['RightFaceLed7', 'RightFaceLed6', 'LeftFaceLed8',
                                       'LeftFaceLed7'])

        self.tracker_service.registerTarget("Face", faceSize)
        self.tracker_service.setMode("Head")
        self.tracker_service.track("Face")
        self.audio_device.setOutputVolume(20) # TODO: Set back to 100 after testing

        self._is_listening = False

        # Start a separate thread to maintain the eye color based on the listening state
        t = threading.Thread(target=self.maintain_eye_color, args=(), daemon=True)
        t.start()

        autonomous_life = session.service("ALAutonomousLife")
        state = autonomous_life.getState()
        logging.info("[PEPPER] ALAutonomousLife state: %s" % state)
        autonomous_life.setState("interactive")
        logging.info("[PEPPER] ALAutonomousLife is now set to interactive")

    def maintain_eye_color(self, interval: float = 0.1):
        """
        Maintain the eye color of the Pepper robot based on the listening state. This method runs in a separate thread and updates the eye color at regular intervals.
        Args:
            interval (float): The time interval (in seconds) between eye color updates (default is 0.1).
        """
        while True:
            try:
                if self._is_listening:
                    self.setListeningEyes()
                else:
                    self.setNonListeningEyes()
            except Exception as e:
                logging.error("[PEPPER] LED update error: %s", e)
            time.sleep(interval)

    def play_audio_file(self, file_number: int):
        """
        Load an audio file based on the given file number, play it with an animation, and wait until the playback is finished before returning.
        Args:
            file_number (int): The number of the audio file to play (e.g., if file_number is 1, it will play "pepper_response_1.mp3").
        """
        audio_file = "/home/nao/pepper_response_" + str(file_number) + ".mp3"
        # Play audio with animation
        logging.info("[PEPPER] Playing audio file: " + audio_file)

        fileID = self.player.loadFile(audio_file)
        self.animation_player_service.run("animations/Stand/Gestures/Explain_5", _async=True)
        self.player.play(fileID)

    def setNonListeningEyes(self):
        """
        Set eyes to white - Non-listening state
        """
        self.leds.fadeRGB('Eyes', 1, 1, 1, 0)

    def setListeningEyes(self):
        """
        Set eyes to green - Listening state
        """
        self.leds.fadeRGB('Eyes', 0, 1, 0, 0)

    def startProcessing(self):
        """
        Main processing loop for the PepperRunner. This method establishes a socket connection to receive commands and data, processes them, and interacts with the Pepper robot's services accordingly.
        """
        # Initialize socket connection on the robot to receive commands and data from an external source (e.g., a server or another application)
        server_socket = socket.socket()

        while True:
            try:
                server_socket.connect((self.host_ip, self.port_number))  # connect to the server
                break
            except:
                time.sleep(1)

        while True:
            try:
                logging.info("[PEPPER] Waiting to receive message")
                message = server_socket.recv(1024 * 4).decode('utf-8')
                logging.info("[PEPPER] Received message: " + message)

                if message == "_stop_listening":
                    self._is_listening = False
                elif message.startswith("_sending"):
                    self._is_listening = False
                    # Extract file number and play audio
                    file_number = message.replace("_sending", "")
                    self.play_audio_file(int(file_number))
                    server_socket.send("reproducing".encode())
                elif message == "_end_sequence":
                    self._is_listening = True
                    server_socket.send("done".encode())
                elif message == "_final":
                    self._is_listening = False
                    logging.info("[PEPPER] Received final message, turning to rest mode and closing connection.")
                    self.motion_service.rest()
                    self.audio_device.setOutputVolume(10)
                    server_socket.close()
                    break
                else:
                    pass

            except Exception as e:
                logging.error("[PEPPER] Error in message processing loop: " + str(e))
                break

        logging.info("[PEPPER] Exiting message processing loop.")


def init_pepper(ip_address: str, port_number: int = 9559, face_size: float = 0.1, host_ip: str = "127.0.0.1", host_port_number: int = 5001):
    """
    Initialize the Pepper robot connection and start the local runner for command processing and data sending.

    Args:
        ip_address (str): The IP address of the Pepper robot.
        port_number (int): The port number for the socket connection. Default is 9559.
        face_size (float): The size of the face to track (default is 0.1).
        host_ip (str): The IP address of the host machine. Default is "127.0.0.1".
        host_port_number (int): The port number for the host machine's socket connection. Default is 5001.
    """

    try:
        # Initialize qi framework.
        connection_url = "tcp://" + ip_address + ":" + str(port_number)
        app = qi.Application(["PepperRunner", "--qi-url=" + connection_url])
        print("Connected to Naoqi at ip \"" + ip_address + "\" on port " + str(port_number) + ".")
    except RuntimeError:
        print("Can't connect to Naoqi at ip \"" + ip_address + "\" on port " + str(port_number) + ".\n")
        sys.exit(1)

    MySoundProcessingModule = PepperRunner(app, face_size, host_ip, host_port_number)
    app.session.registerService("PepperRunner", MySoundProcessingModule)
    MySoundProcessingModule.startProcessing()
    app.stop()
