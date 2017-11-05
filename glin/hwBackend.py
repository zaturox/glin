import socket
import numpy as np

class AbstractHwBackend:
    def __init__(self, numLed, config):
        pass
    def connect(self):
        pass
    def switchOff(self):
        pass
    def switchOn(self):
        pass
    def send(self, data):
        pass
    def disconnect(self):
        pass

class UDP(AbstractHwBackend):
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
