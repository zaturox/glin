import socket
import numpy as np

class UDP:
    def connect(self):
        pass
    def prepare(self, numLed):
        self.numLed = numLed
    def switchOff(self):
        self.send(np.zeros(3*self.numLed))
    def switchOn(self):
        pass
    def send(self, data):
        UDP_IP = "localhost"
        UDP_PORT = 5005
        buf = (255*data).astype(np.uint8)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(buf, (UDP_IP, UDP_PORT))
    def disconnect(self):
        pass