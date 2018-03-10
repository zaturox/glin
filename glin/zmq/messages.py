"""constructs and parses multipart zeromq messages"""

from struct import pack
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
