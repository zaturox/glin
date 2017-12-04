import socket
import numpy as np

class AbstractHwBackend:
    """Base Class for hardware communication"""
    def __init__(self, numLed, config):
        pass
    def connect(self):
        """Connect to target"""
        pass
    def switchOff(self):
        """Turn LED stripe off. LEDs should not be on after this call"""
        pass
    def switchOn(self):
        """turn hardware on, wait for data"""
        pass
    def send(self, data):
        """send color data to LEDs"""
        pass
    def disconnect(self):
        """Disconnect from target"""
        pass
    def maxFps(self):
        """report maximum available frames per second to glin core"""
        return float('inf')

class UDP(AbstractHwBackend):
    """Communicate to LED Stripe via UDP"""
    def __init__(self, numLed, config):
        self.numLed = numLed
        self.host = config["host"]
        self.port = int(config["port"])
        self.sock = None
    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    def switchOff(self):
        self.send(np.zeros(3*self.numLed))
    def switchOn(self):
        pass
    def send(self, data):
        buf = (255*data).astype(np.uint8)
        self.sock.sendto(buf, (self.host, self.port))
    def disconnect(self):
        self.sock = None
    def maxFps(self):
        return 100
