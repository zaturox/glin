"""constructs and parses multipart zeromq messages"""
import numpy as np
from struct import pack, unpack
import types

class MessageBuilder:
    """generates multiframe zeromq messages"""
    @staticmethod
    def brightness(seqNr, brightness):
        return MessageWriter().string("brightness").uint64(seqNr).uint8(int(brightness*255)).get()
    @staticmethod
    def mainswitch(seqNr, state):
        return MessageWriter().string("mainswitch.state").uint64(seqNr).bool(state).get()
    @staticmethod
    def animationAdd(seqNr, animationId, animationName):
        return MessageWriter().string("animation.add").uint64(seqNr).uint32(animationId).string(animationName).get()
    @staticmethod
    def sceneActive(seqNr, sceneId):
        return MessageWriter().string("scene.setactive").uint64(seqNr).uint32(sceneId).get()
    @staticmethod
    def sceneAdd(seqNr, sceneId, animationId, name, color, velocity, config):
        (red, green, blue) = (int(color[0]*255),int(color[1]*255),int(color[2]*255))
        return MessageWriter().string("scene.add").uint64(seqNr).uint32(sceneId).uint32(animationId).string(name).uint8_3(red, green, blue).uint32(int(velocity * 1000)).string(config).get()
    @staticmethod
    def sceneRemove(seqNr, sceneId):
        return MessageWriter().string("scene.rm").uint64(seqNr).uint32(sceneId).get()
    @staticmethod
    def sceneName(seqNr, sceneId, name):
        return MessageWriter().string("scene.name").uint64(seqNr).uint32(sceneId).string(name).get()
    @staticmethod
    def sceneConfig(seqNr, sceneId, config):
        return MessageWriter().string("scene.config").uint64(seqNr).uint32(sceneId).string(config).get()
    @staticmethod
    def sceneColor(seqNr, sceneId, color):
        return MessageWriter().string("scene.color").uint64(seqNr).uint32(sceneId).uint8_3(int(color[0]*255), int(color[1]*255), int(color[2]*255)).get()
    @staticmethod
    def sceneVelocity(seqNr, sceneId, velocity):
        return MessageWriter().string("scene.velocity").uint64(seqNr).uint32(sceneId).uint32(int(velocity*1000)).get()

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
        self.msg += [ b"\x01" if val else b"\x00"]
        return self
    # integer types
    def uint8(self, val):
        """append a frame containing a uint8"""
        self.msg += [pack("B", val)]
        return self
    def uint8_3(self, v1, v2, v3):
        """append a frame containing 3 uint8"""
        self.msg += [pack("BBB", v1,v2,v3)]
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
    pass

class MessageParser:
    """parses a multiframe ZeroMQ message"""
    @staticmethod
    def mainswitch(frames):
        """parse a mainswitch.state message"""
        reader = MessageReader(frames)
        res = reader.string("command").bool("state").assert_end().get()
        return (res.state,)

    @staticmethod
    def sceneAdd(frames):
        """parse a scene.add message"""
        reader = MessageReader(frames)
        results = reader.string("command").uint32("animationId").string("name").uint8_3("color").uint32("velocity").string("config").get()
        if results.command != "scene.add":
            raise MessageParserError("Command is not 'scene.add'")
        return (results.animationId, results.name, np.array([results.color[0]/255, results.color[1]/255, results.color[2]/255]),
                results.velocity/1000, results.config)

    @staticmethod
    def sceneColor(frames):
        """parse a scene.color message"""
        # "scene.color" <sceneId> <color>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("sceneId").uint8_3("color").assert_end().get()
        if results.command != "scene.color":
            raise MessageParserError("Command is not 'scene.color'")
        return (results.sceneId, np.array([results.color[0]/255, results.color[1]/255, results.color[2]/255]))

    @staticmethod
    def sceneConfig(frames):
        """parse a scene.config message"""
        # "scene.velocity" <sceneId> <config>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("sceneId").string("config").assert_end().get()
        if results.command != "scene.config":
            raise MessageParserError("Command is not 'scene.config'")
        return (results.sceneId, results.config)

    @staticmethod
    def sceneName(frames):
        """parse a scene.name message"""
        # "scene.velocity" <sceneId> <config>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("sceneId").string("name").assert_end().get()
        if results.command != "scene.name":
            raise MessageParserError("Command is not 'scene.name'")
        return (results.sceneId, results.name)

    @staticmethod
    def sceneRemove(frames):
        """parse a scene.rm message"""
        # "scene.velocity" <sceneId>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("sceneId").assert_end().get()
        if results.command != "scene.rm":
            raise MessageParserError("Command is not 'scene.rm'")
        return (results.sceneId,)

    @staticmethod
    def sceneSetactive(frames):
        """parse a scene.rm message"""
        # "scene.setactive" <sceneId>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("sceneId").assert_end().get()
        if results.command != "scene.setactive":
            raise MessageParserError("Command is not 'scene.setactive'")
        return (results.sceneId,)

    @staticmethod
    def sceneVelocity(frames):
        """parse a scene.velocity message"""
        # "scene.velocity" <sceneId> <velocity>
        reader = MessageReader(frames)
        results = reader.string("command").uint32("sceneId").uint32("velocity").assert_end().get()
        if results.command != "scene.velocity":
            raise MessageParserError("Command is not 'scene.velocity'")
        return (results.sceneId, results.velocity/1000)

class MessageReader:
    """read message frame by frame"""
    def __init__(self, frames):
        self.frames = frames
        self.results = types.SimpleNamespace()

    def assert_end(self):
        if len(self.frames) != 0:
            raise MessageParserError("Expected end of frames, but there are frames left")
        return self
    def get(self):
        """return parsed message"""
        return self.results
    # common
    def _assert_is_string(self, name):
        if not isinstance(name, str):        
            raise TypeError("Name has to be String")
    def _nextFrame(self):
        try:
            return self.frames.pop(0)
        except IndexError as err:
            raise MessageParserError("ZeroMQ message has to few frames") from err
    # string types
    def string(self, name):
        """parse a string frame"""
        self._assert_is_string(name)
        f = self._nextFrame()
        try:
            val = f.decode('utf-8')
            self.results.__dict__[name] = val
        except UnicodeError as err:
            raise MessageParserError("Message contained invalid Unicode characters") \
                from err
        return self
    # Boolean
    def bool(self, name):
        """parse a boolean frame"""
        self._assert_is_string(name)
        f = self._nextFrame()
        if len(f) != 1:
            raise MessageParserError("Expected exacty 1 byte for boolean value")
        val = f != b"\x00"
        self.results.__dict__[name] = val
        return self
    # integer
    def uint8_3(self, name):
        self._assert_is_string(name)
        f = self._nextFrame()
        if len(f) != 3:
            raise MessageParserError("Expected exacty 4 byte for uint32 value")
        vals = unpack("BBB", f)
        self.results.__dict__[name] = vals
        return self
    def uint32(self, name):
        self._assert_is_string(name)
        f = self._nextFrame()
        if len(f) != 4:
            raise MessageParserError("Expected exacty 4 byte for uint32 value")
        (val,) = unpack("!I", f)
        self.results.__dict__[name] = val
        return self
