"""Communication with LED Hardware"""

import socket
import numpy as np

class AbstractHwBackend:
    """Base Class for hardware communication"""
    def __init__(self, led_count, config):
        pass
    def connect(self):
        """Connect to target"""
        pass
    def switch_off(self):
        """Turn LED stripe off. LEDs should not be on after this call"""
        pass
    def switch_on(self):
        """turn hardware on, wait for data"""
        pass
    def send(self, data):
        """send color data to LEDs"""
        pass
    def disconnect(self):
        """Disconnect from target"""
        pass
    def get_max_fps(self):
        """report maximum available frames per second to glin core"""
        return float('inf')

class UDP(AbstractHwBackend):
    """Communicate to LED Stripe via UDP"""
    def __init__(self, led_count, config):
        super().__init__(led_count, config)
        self.led_count = led_count
        self.host = config["host"]
        self.port = int(config["port"])
        self.sock = None
    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    def switch_off(self):
        self.send(np.zeros(3*self.led_count))
    def switch_on(self):
        pass
    def send(self, data):
        buf = (255*data).astype(np.uint8).flatten()
        self.sock.sendto(buf, (self.host, self.port))
    def disconnect(self):
        self.sock = None
    def get_max_fps(self):
        return 100
