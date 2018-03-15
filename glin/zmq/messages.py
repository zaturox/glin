"""constructs and parses multipart zeromq messages"""

import types
from struct import pack, unpack
import numpy as np

class MessageBuilder:
    """generates multiframe zeromq messages"""
    @staticmethod
    def brightness(sequence_number, brightness):
        """Create a brightness message"""
        return MessageWriter().string("brightness").uint64(sequence_number).uint8(int(brightness*255)).get()
    @staticmethod
    def mainswirch_state(sequence_number, state):
        """Create a mainswitch.state message"""
        return MessageWriter().string("mainswitch.state").uint64(sequence_number).bool(state).get()
    @staticmethod
    def animation_add(sequence_number, animation_id, name):
        """Create a animation.add message"""
        return MessageWriter().string("animation.add").uint64(sequence_number).uint32(animation_id).string(name).get()
    @staticmethod
    def scene_active(sequence_number, scene_id):
        """Create a scene.setactive message"""
        return MessageWriter().string("scene.setactive").uint64(sequence_number).uint32(scene_id).get()
    @staticmethod
    def scene_add(sequence_number, scene_id, animation_id, name, color, velocity, config):
        """Create a scene.add message"""
        (red, green, blue) = (int(color[0]*255), int(color[1]*255), int(color[2]*255))
        return MessageWriter().string("scene.add").uint64(sequence_number).uint32(scene_id).uint32(animation_id).string(name) \
                              .uint8_3(red, green, blue).uint32(int(velocity * 1000)).string(config).get()
    @staticmethod
    def scene_remove(sequence_number, scene_id):
        """Create a scene.rm message"""
        return MessageWriter().string("scene.rm").uint64(sequence_number).uint32(scene_id).get()
    @staticmethod
    def scene_name(sequence_number, scene_id, name):
        """Create a scene.name message"""
        return MessageWriter().string("scene.name").uint64(sequence_number).uint32(scene_id).string(name).get()
    @staticmethod
    def scene_config(sequence_number, scene_id, config):
        """Create a scene.config message"""
        return MessageWriter().string("scene.config").uint64(sequence_number).uint32(scene_id).string(config).get()
    @staticmethod
    def scene_color(sequence_number, scene_id, color):
        """Create a scene.color message"""
        return MessageWriter().string("scene.color").uint64(sequence_number).uint32(scene_id) \
                              .uint8_3(int(color[0]*255), int(color[1]*255), int(color[2]*255)).get()
    @staticmethod
    def scene_velocity(sequence_number, scene_id, velocity):
        """Create a scene.velocity message"""
        return MessageWriter().string("scene.velocity").uint64(sequence_number).uint32(scene_id).uint32(int(velocity*1000)).get()

class MessageWriter:
    """builds zeromq messages frame by frame"""
    def __init__(self):
        self.msg = []
    def get(self):
        """get the final multipart message"""
        return self.msg
    # String types
    def string(self, val):
        """append a frame containing a string"""
        self.msg += [val.encode('utf-8')]
        return self
    # Boolean
    def bool(self, val):
        """append a frame containing a boolean"""
        self.msg += [b"\x01" if val else b"\x00"]
        return self
    # integer types
    def uint8(self, val):
        """append a frame containing a uint8"""
        self.msg += [pack("B", val)]
        return self
    def uint8_3(self, val1, val2, val3):
        """append a frame containing 3 uint8"""
        self.msg += [pack("BBB", val1, val2, val3)]
        return self
    def uint32(self, val):
        """append a frame containing a uint32"""
        self.msg += [pack("!I", val)]
        return self
    def uint64(self, val):
        """append a frame containing a uint64"""
        self.msg += [pack("!Q", val)]
        return self

class MessageParserError(Exception):
    """This Error is raised if an error happens while creating or parsing a ZeroMQ message"""
    pass

class MessageParser:
    """parses a multiframe ZeroMQ message"""
    @staticmethod
    def mainswirch_state(frames):
        """parse a mainswitch.state message"""
        reader = MessageReader(frames)
        res = reader.string("command").bool("state").assert_end().get()
        return (res.state,)

    @staticmethod
    def scene_add(frames):
        """parse a scene.add message"""
        reader = MessageReader(frames)
        results = reader.string("command").uint32("animation_id").string("name").uint8_3("color").uint32("velocity").string("config").get()
        if results.command != "scene.add":
            raise MessageParserError("Command is not 'scene.add'")
        return (results.animation_id, results.name, np.array([results.color[0]/255, results.color[1]/255, results.color[2]/255]),
                results.velocity/1000, results.config)

    @staticmethod
    def scene_color(frames):
        """parse a scene.color message"""
        # "scene.color" <scene_id> <color>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("scene_id").uint8_3("color").assert_end().get()
        if results.command != "scene.color":
            raise MessageParserError("Command is not 'scene.color'")
        return (results.scene_id, np.array([results.color[0]/255, results.color[1]/255, results.color[2]/255]))

    @staticmethod
    def scene_config(frames):
        """parse a scene.config message"""
        # "scene.velocity" <scene_id> <config>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("scene_id").string("config").assert_end().get()
        if results.command != "scene.config":
            raise MessageParserError("Command is not 'scene.config'")
        return (results.scene_id, results.config)

    @staticmethod
    def scene_name(frames):
        """parse a scene.name message"""
        # "scene.velocity" <scene_id> <config>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("scene_id").string("name").assert_end().get()
        if results.command != "scene.name":
            raise MessageParserError("Command is not 'scene.name'")
        return (results.scene_id, results.name)

    @staticmethod
    def scene_remove(frames):
        """parse a scene.rm message"""
        # "scene.velocity" <scene_id>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("scene_id").assert_end().get()
        if results.command != "scene.rm":
            raise MessageParserError("Command is not 'scene.rm'")
        return (results.scene_id,)

    @staticmethod
    def scene_active(frames):
        """parse a scene.rm message"""
        # "scene.setactive" <scene_id>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("scene_id").assert_end().get()
        if results.command != "scene.setactive":
            raise MessageParserError("Command is not 'scene.setactive'")
        return (results.scene_id,)

    @staticmethod
    def scene_velocity(frames):
        """parse a scene.velocity message"""
        # "scene.velocity" <scene_id> <velocity>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("scene_id").uint32("velocity").assert_end().get()
        if results.command != "scene.velocity":
            raise MessageParserError("Command is not 'scene.velocity'")
        return (results.scene_id, results.velocity/1000)

class MessageReader:
    """read message frame by frame"""
    def __init__(self, frames):
        self.frames = frames
        self.results = types.SimpleNamespace()

    def assert_end(self):
        """Assert, that there is no frame left for parsing"""
        if self.frames: # List evaluates to false if it es empty, otherwise to true
            raise MessageParserError("Expected end of frames, but there are frames left")
        return self
    def get(self):
        """return parsed message"""
        return self.results
    # common
    def _assert_is_string(self, name):
        if not isinstance(name, str):
            raise TypeError("Name has to be String")
    def _next_frame(self):
        try:
            return self.frames.pop(0)
        except IndexError as err:
            raise MessageParserError("ZeroMQ message has to few frames") from err
    # string types
    def string(self, name):
        """parse a string frame"""
        self._assert_is_string(name)
        frame = self._next_frame()
        try:
            val = frame.decode('utf-8')
            self.results.__dict__[name] = val
        except UnicodeError as err:
            raise MessageParserError("Message contained invalid Unicode characters") \
                from err
        return self
    # Boolean
    def bool(self, name):
        """parse a boolean frame"""
        self._assert_is_string(name)
        frame = self._next_frame()
        if len(frame) != 1:
            raise MessageParserError("Expected exacty 1 byte for boolean value")
        val = frame != b"\x00"
        self.results.__dict__[name] = val
        return self
    # integer
    def uint8_3(self, name):
        """parse a tuple of 3 uint8 values"""
        self._assert_is_string(name)
        frame = self._next_frame()
        if len(frame) != 3:
            raise MessageParserError("Expected exacty 3 byte for 3 unit8 values")
        vals = unpack("BBB", frame)
        self.results.__dict__[name] = vals
        return self
    def uint32(self, name):
        """parse a uint32 value"""
        self._assert_is_string(name)
        frame = self._next_frame()
        if len(frame) != 4:
            raise MessageParserError("Expected exacty 4 byte for uint32 value")
        (val,) = unpack("!I", frame)
        self.results.__dict__[name] = val
        return self
