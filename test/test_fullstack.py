import threading
import unittest

import zmq

import glin.__main__

class FullstackTestMethods(unittest.TestCase):
    def setUp(self):
        self.appThread = threading.Thread(target=glin.__main__.boot, daemon=True)
        self.appThread.start()
    def test_fullstack(self):
        ctx = zmq.Context()
        req_socket = ctx.socket(zmq.REQ)
        req_socket.setsockopt(zmq.RCVTIMEO, 1000)
        req_socket.connect("tcp://localhost:6607")
        sub_socket = ctx.socket(zmq.SUB)
        sub_socket.setsockopt(zmq.RCVTIMEO, 1000)
        sub_socket.connect("tcp://localhost:6606")
        sub_socket.setsockopt(zmq.SUBSCRIBE, b"")
        
        # first set mainswitch to a defined state
        req_socket.send_multipart([b"mainswitch.state", b"\x01"])
        msg = req_socket.recv_multipart()
        if msg[0] != b"\x00":
            sub_socket.recv_multipart()
        
        req_socket.send_multipart([b"mainswitch.state", b"\x01"])
        msg = req_socket.recv_multipart()
        self.assertEqual(msg[0], b"\x00", "Expected False because mainswitch shoudl already be On")

        req_socket.send_multipart([b"mainswitch.state", b"\x00"])
        msg = req_socket.recv_multipart()
        self.assertNotEqual(msg[0], b"\x00")

        req_socket.send_multipart([b"brightness", b"\x00\x00\x00\xFA"])
        msg = req_socket.recv_multipart()
        self.assertNotEqual(msg[0], b"\x00")


