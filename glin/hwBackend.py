import socket
import numpy as np

class UDP:
    EXT_NAME = "udp"   # this class is referenced in config file by this identifier
    def __init__(self, numLed, config):
        self.numLed = numLed
        self.host = config["host"]
        self.port = int(config["port"])
    def connect(self):
        pass
    def switchOff(self):
        self.send(np.zeros(3*self.numLed))
    def switchOn(self):
        pass
    def send(self, data):
        buf = (255*data).astype(np.uint8)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(buf, (self.host, self.port))
    def disconnect(self):
        pass