import unittest

import numpy as np

from glin.zmq.messages import MessageBuilder as mb
from glin.zmq.messages import MessageParser as mp
from glin.zmq.messages import MessageParserError


class BuilderTestMethods(unittest.TestCase):
    def test_brightness(self):
        msg = mb.brightness(0xABCDEF0123456789, 1.0)
        self.assertEqual(msg, [b"brightness", b"\xAB\xCD\xEF\x01\x23\x45\x67\x89", b"\xFF"])
        msg = mb.brightness(0xABCDEF0123456789, 0.0)
        self.assertEqual(msg, [b"brightness", b"\xAB\xCD\xEF\x01\x23\x45\x67\x89", b"\x00"])
        with self.assertRaises(ValueError):
            mb.brightness("0xABCDEF0123456789", 1.0)
        with self.assertRaises(ValueError):
            mb.brightness(0xABCDEF0123456789, "1.0")
        with self.assertRaises(ValueError):
            mb.brightness(-1, 1.0)

    def test_mainswitch_state(self):
        msg = mb.mainswitch_state(0xABCDEF0123456789, False)
        self.assertEqual(msg, [b"mainswitch.state", b"\xAB\xCD\xEF\x01\x23\x45\x67\x89", b"\x00"])
        
        msg = mb.mainswitch_state(0xABCDEF0123456789, True)
        self.assertEqual(len(msg), 3)
        self.assertEqual(msg[0:2],[b"mainswitch.state", b"\xAB\xCD\xEF\x01\x23\x45\x67\x89"])
        self.assertEqual(len(msg), 3)
        self.assertIsNot(msg[2], b"\x00")

        with self.assertRaises(ValueError):
            mb.mainswitch_state("0xABCDEF0123456789", False)
        with self.assertRaises(ValueError):
            mb.mainswitch_state(-12345, False)
        #with self.assertRaises(ValueError):  # or use pythons evaluation to True or False?! ...
        #    mb.mainswitch_state(0xABCDEF0123456789, "False")  # but this would evaluate to True...

class ParserTestMethods(unittest.TestCase):
    def test_brightness(self):
        r = mp.brightness([b"brightness", b"\x00\x00\x00\x00"])
        self.assertEqual(len(r), 1, "Expected tuple of size 1")
        self.assertAlmostEqual(r[0], 0.00, 3)

        r = mp.brightness([b"brightness", b"\x00\x00\x00\x0A"])
        self.assertEqual(len(r), 1, "Expected tuple of size 1")
        self.assertAlmostEqual(r[0], 0.01, 3)

        r = mp.brightness([b"brightness", b"\x00\x00\x03\xE8"])
        self.assertEqual(len(r), 1, "Expected tuple of size 1")
        self.assertAlmostEqual(r[0], 1.0, 3)

        r = mp.brightness([b"brightness", b"\x00\x00\x44\xB9"])
        self.assertEqual(len(r), 1, "Expected tuple of size 1")
        self.assertAlmostEqual(r[0], 17.593, 3)

        r = mp.brightness([b"brightness", b"\xE4\x93\xE4\xCA"])
        self.assertEqual(len(r), 1, "Expected tuple of size 1")
        self.assertAlmostEqual(r[0], 3834897.610, 3)

        with self.assertRaises(MessageParserError):
            mp.brightness([b"brightness", b"\xE4\x93\xE4"])
        with self.assertRaises(MessageParserError):
            mp.brightness([b"brightness", b"\xE4\x93\xE4\xCA\x68\x21\x00\x82"])
        with self.assertRaises(MessageParserError):
            mp.brightness([b"brightness", b"\xE4\x93\xE4\xCA", b"\x12\x34\x56\x78"])
        with self.assertRaises(MessageParserError):
            mp.brightness([b"brightnessFOO", b"\xE4\x93\xE4\xCA"])
        with self.assertRaises(MessageParserError):
            mp.brightness([b"brightnes", b"\xE4\x93\xE4\xCA"])

    def test_mainswtich_state(self):
        r = mp.mainswitch_state([b"mainswitch.state", b"\x00"])
        self.assertEqual(r, (False,))
        r = mp.mainswitch_state([b"mainswitch.state", b"\x01"])
        self.assertEqual(r, (True,))
        r = mp.mainswitch_state([b"mainswitch.state", b"\x02"])
        self.assertEqual(r, (True,))
        r = mp.mainswitch_state([b"mainswitch.state", b"\xFE"])
        self.assertEqual(r, (True,))
        r = mp.mainswitch_state([b"mainswitch.state", b"\xFF"])
        self.assertEqual(r, (True,))
        with self.assertRaises(MessageParserError):
            mp.mainswitch_state([b"mainswitch.stat", b"\x01"])
        with self.assertRaises(MessageParserError):
            mp.mainswitch_state([b"mainswitch.stat", b"\x00\x01"])
        with self.assertRaises(MessageParserError):
            mp.mainswitch_state([b"mainswitch.stat", b"\x01", b"\x00"])
    def test_scene_add(self):
        # scene_add(animation_id, name, color, velocity, config):
        r = mp.scene_add([b"scene.add", b"\x10\x01\x43\x78", "$p€ciä|. #char".encode("utf-8"),
                          b"\x32\x01\xde", b"\x00\x23\x12\xFE", b"configuration"])
        #self.assertEqual(r, (0x10014378, "$p€ciä|. #char", np.array([0x32/255, 0x01/255, 0xDE/255]), 2298.622, "configuration"))

