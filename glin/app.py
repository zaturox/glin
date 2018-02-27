"""Glin Server - Manage Animations for LED Stripes"""

import datetime
import logging
from collections import namedtuple
from struct import pack, unpack
from types import SimpleNamespace

import numpy as np
import zmq
from zmq.eventloop.ioloop import IOLoop, PeriodicCallback
from zmq.eventloop.zmqstream import ZMQStream

Scene = namedtuple('Scene', 'animationId name color velocity config')

class GlinApp:
    """Main Class for Management"""
    def __init__(self, numLed, hwBackend, port=6606):
        self.ctx = zmq.Context()
        self.numLed = numLed
        self.port = port

        self.loop = IOLoop.instance()
        self.caller = PeriodicCallback(self._on_nextFrame, 1000/30, self.loop)
        self.hwComm = hwBackend
        self.hwComm.connect()
        self.zmqCollector = GlinAppZmqCollector(self, self.ctx)
        self.zmqPublisher = GlinAppZmqPublisher(self, self.ctx)

        # server side configuration
        self.config = SimpleNamespace()
        self.config.maxFps = 60

        # current state (somehow client side configuration)
        self.state = SimpleNamespace()
        self.state.animationClasses = []
        self.state.activeSceneId = None
        self.state.activeAnimation = None
        self.state.scenes = {}
        self.state.brightness = 1.0
        self.state.sceneIdCtr = 0
        self.state.mainswitch = True
        self.state.targetFps = 0
        self.state.lastFrameSent = None

    def setBrightness(self, brightness):
        """set brightness in range 0...1"""
        brightness = min([1.0, max([brightness, 0.0])]) # enforces range 0 ... 1
        self.state.brightness = brightness
        self._repeatLastFrame()
        seqNr = self.zmqPublisher.publishBrightness(brightness)
        logging.debug("Set brightness to {brightPercent:05.1f}%".format(brightPercent=brightness*100))
        return (True, seqNr, "OK")

    def registerAnimation(self, animType):
        """Add a new animation"""
        self.state.animationClasses.append(animType)
        return len(self.state.animationClasses) - 1

    def registerScene(self, animationId, sceneName, color, velocity, config):
        """Add a new scene, returns Scene ID"""
        # check arguments
        if animationId < 0 or animationId >= len(self.state.animationClasses):
            err_msg = "Requested to register scene with invalid Animation ID. Out of range."
            logging.info(err_msg)
            return(False, 0, err_msg)
        if self.state.animationClasses[animationId].checkConfig(config) == False:
            err_msg = "Requested to register scene with invalid configuration."
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.sceneIdCtr += 1
        self.state.scenes[self.state.sceneIdCtr] = Scene(animationId, sceneName, color, velocity, config)
        seqNr = self.zmqPublisher.publishAddScene(self.state.sceneIdCtr, animationId, sceneName, color, velocity, config)
        logging.debug("Registered new scene.")

        # set this scene as active scene if none is configured yet
        if self.state.activeSceneId is None:
            self.setActiveScene(self.state.sceneIdCtr)
        return (True, seqNr, "OK")

    def removeScene(self, sceneId):
        """remove a scene by Scene ID"""
        if self.state.activeSceneId == sceneId:
            err_msg = "Requested to delete scene {sceneNum}, which is currently active. Cannot delete active scene.".format(sceneNum=sceneId)
            logging.info(err_msg)
            return(False, 0, err_msg)
        try:
            del self.state.scenes[sceneId]
            logging.debug("Deleted scene {sceneNum}".format(sceneNum=sceneId))
        except KeyError:
            err_msg = "Requested to delete scene {sceneNum}, which does not exist".format(sceneNum=sceneId)
            logging.info(err_msg)
            return(False, 0, err_msg)
        # if we are here, we deleted a scene, so publish it
        seqNr = self.zmqPublisher.publishRemoveScene(sceneId)
        logging.debug("Removed scene {sceneNum}".format(sceneNum=sceneId))
        return (True, seqNr, "OK")

    def renameScene(self, sceneId, name):
        """rename a scene by scene ID"""
        if not sceneId in self.state.scenes: # does that sceneId exist?
            err_msg = "Requested to rename scene {sceneNum}, which does not exist".format(sceneNum=sceneId)
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.scenes[sceneId] = self.state.scenes[sceneId]._replace(name=name) # TODO: is there a better solution?
        seqNr = self.zmqPublisher.publishRenameScene(sceneId, name)
        logging.debug("Renamed scene {sceneNum}".format(sceneNum=sceneId))
        return (True, seqNr, "OK")

    def reconfigScene(self, sceneId, config):
        """reconfigure a scene by scene ID"""
        if not sceneId in self.state.scenes: # does that sceneId exist?
            err_msg = "Requested to reconfigure scene {sceneNum}, which does not exist".format(sceneNum=sceneId)
            logging.info(err_msg)
            return(False, 0, err_msg)
        if sceneId == self.state.activeSceneId:
            pass  # TODO: maybe calculate next frame, esp. if static scene
        self.state.scenes[sceneId] = self.state.scenes[sceneId]._replace(config=config)
        seqNr = self.zmqPublisher.publishReconfigScene(sceneId, config)
        logging.debug("Reconfigured scene {sceneNum}".format(sceneNum=sceneId))
        return (True, seqNr, "OK")

    def recolorScene(self, sceneId, color):
        """reconfigure a scene by scene ID"""
        if not sceneId in self.state.scenes: # does that sceneId exist?
            err_msg = "Requested to recolor scene {sceneNum}, which does not exist".format(sceneNum=sceneId)
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.scenes[sceneId] = self.state.scenes[sceneId]._replace(color=color)
        seqNr = self.zmqPublisher.publishRecolorScene(sceneId, color)
        logging.debug("Recolored scene {sceneNum}".format(sceneNum=sceneId))
        if sceneId == self.state.activeSceneId:
            self.state.activeAnimation.setColor(color)
            self._doNextFrame() # TODO: make it more sensible, e.g. call only if static scene
        return (True, seqNr, "OK")

    def velocityScene(self, sceneId, velocity):
        """reconfigure a scene by scene ID"""
        if not sceneId in self.state.scenes: # does that sceneId exist?
            err_msg = "Requested to set velocity on scene {sceneNum}, which does not exist".format(sceneNum=sceneId)
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.scenes[sceneId] = self.state.scenes[sceneId]._replace(velocity=velocity)
        seqNr = self.zmqPublisher.publishVelocityScene(sceneId, velocity)
        logging.debug("set velocity on scene {sceneNum}".format(sceneNum=sceneId))
        if sceneId == self.state.activeSceneId:
            self.state.activeAnimation.setVelocity(velocity)
            self._doNextFrame() # TODO: make it more sensible, e.g. call only if static scene
        return (True, seqNr, "OK")

    def setActiveScene(self, sceneId):
        """sets the active scene by scene ID"""
        if self.state.activeSceneId != sceneId: # do nothing if scene has not changed
            self._deactivateScene()
            seqNr = self.zmqPublisher.publishActiveScene(sceneId)
            self.state.activeSceneId = sceneId
            if self.state.mainswitch is True: # activate scene only if we are switched on
                self._activateScene()
            logging.debug("Set scene {sceneNum} as active scene".format(sceneNum=sceneId))
            return (True, seqNr, "OK")
        else:
            logging.debug("Scene {sceneNum} already is active scene".format(sceneNum=sceneId))
            return (False, 0, "This already is the activated scene.")

    def setMainSwitch(self, state):
        """Turns output on or off. Also turns hardware on ir off"""
        if self.state.mainswitch == state:
            err_msg = "MainSwitch unchanged, already is {sState}".format(sState="On" if state else "Off") # fo obar lorem ipsum
            logging.debug(err_msg) # fo obar lorem ipsum
            return (False, 0, err_msg) # because nothing changed
        self.state.mainswitch = state
        seqNr = self.zmqPublisher.publishMainSwitch(state)
        logging.debug("MainSwitch toggled, new state is {sState}".format(sState="On" if state else "Off")) # fo obar lorem ipsum
        if state is True:
            self.hwComm.switchOn()
            self._activateScene() # reinit scene
        else:
            self._deactivateScene()
            self.hwComm.switchOff()
        return (True, seqNr, "OK")

    def _activateScene(self):
        if self.state.activeSceneId in self.state.scenes: # is sceneId valid? if not, assume there is no scene configured
            animClass = self.state.animationClasses[self.state.scenes[self.state.activeSceneId].animationId]
            self.state.activeAnimation = animClass()
            targetFps = min( self.config.maxFps, self.state.activeAnimation.maxFps(), self.hwComm.maxFps() )
            if targetFps < 0:
                targetFps = 0
            self.state.targetFps = targetFps
            logging.debug("Running with {fps} FPS".format(fps=targetFps))
            self.state.activeAnimation.prepare(self.numLed, targetFps)
            self.state.activeAnimation.setColor(self.state.scenes[self.state.activeSceneId].color)
            self.state.activeAnimation.setVelocity(self.state.scenes[self.state.activeSceneId].velocity)
            self.state.activeAnimation.setConfig(self.state.scenes[self.state.activeSceneId].config)
            if targetFps > 0:   # 0 FPS means one-shot -> no periodic callback required
                self.caller.callback_time = 1000/targetFps
                self.caller.start()
            self.loop.add_callback_from_signal(self._doNextFrame) # execute once to not have to wait for periodic callback (self.caller), esp. if 0 or low FPS
        else:
            self.state.activeAnimation = None # don't do anything. stuck with last frame.

    def _deactivateScene(self):
        if not self.state.activeAnimation is None:
            self.caller.stop() # stop rendering new frames
            self.state.activeAnimation.finish()
            self.state.activeAnimation = None

    def toggleMainSwitch(self):
        """Toggles the mainswitch state"""
        return self.setMainSwitch(not self.state.mainswitch)

    def _on_nextFrame(self):
        logging.debug("generating next frame")
        self._doNextFrame()

    def _doNextFrame(self):
        if self.state.activeAnimation:
            buf = np.zeros((self.numLed, 3))
            self.state.activeAnimation.nextFrame(buf)
            self.state._buf = np.copy(buf)
            self._sendFrame(buf)
        else:
            logging.debug("app: No Active Animation")

    def _repeatLastFrame(self):
        # only do something, if there is an active animation, else output is considered to be turned off
        if hasattr(self.state, '_buf') and self.state._buf is not None and self.state.activeAnimation is not None:
            if self.state.targetFps < self.config.maxFps / 4: # to not overload hwbackend, only resend, if active animation is very slow
                self._sendFrame(np.copy(self.state._buf))

    def _repeatFrame(self):
        pass # TODO: if color/config/... changed, calculate a new frame and send it out, esp. for static scenes

    def _sendFrame(self, buf):
        np.clip(buf, 0.0, 1.0, out=buf)
        self.state.lastFrameSent = datetime.datetime.now()
        buf *= self.state.brightness
        self.hwComm.send(buf)

    def execute(self):
        """Execute Main Loop"""
        try:
            logging.debug("Entering IOLoop")
            self.loop.start()
            logging.debug("Leaving IOLoop")
        except KeyboardInterrupt:
            logging.debug("Leaving IOLoop by KeyboardInterrupt")
        finally:
            self.hwComm.disconnect()


class GlinAppZmqPublisher:
    """Publishes state changes via ZeroMQ Push Socket"""
    def __init__(self, app, ctx, port=6606):
        self.app = app
        self.ctx = ctx
        self.publisher = self.ctx.socket(zmq.PUB)
        self.publisher.bind("tcp://*:" + str(port))
        self.snapshot = ctx.socket(zmq.ROUTER)
        self.snapshot.bind("tcp://*:" + str(port+2))
        self.snapshot = ZMQStream(self.snapshot)
        self.snapshot.on_recv(self.handle_snapshot)
        self.seqNr = 0

    def publishBrightness(self, brightness):
        self.seqNr += 1
        self.publisher.send_multipart([b"brightness", pack("!Q", self.seqNr), pack("B", int(brightness*255))])
        return self.seqNr
    def publishMainSwitch(self, state):
        self.seqNr += 1
        self.publisher.send_multipart([b"mainswitch.state", pack("!Q", self.seqNr), b"\x01" if state else b"\x00"])
        return self.seqNr
    def publishActiveScene(self, sceneId):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.setactive", pack("!Q", self.seqNr), pack("!I", sceneId)])
        return self.seqNr
    def publishAddScene(self, sceneId, animationId, name, color, velocity, config):
        self.seqNr += 1
        (red, green, blue) = (int(color[0]*255),int(color[1]*255),int(color[2]*255))
        self.publisher.send_multipart([b"scene.add", pack("!Q", self.seqNr), pack("!I", sceneId), pack("!I", animationId), name.encode('utf-8'), pack("BBB", red, green, blue), pack("!I", int(velocity * 1000)), config.encode('utf-8')])
        return self.seqNr
    def publishRemoveScene(self, sceneId):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.rm", pack("!Q", self.seqNr), pack("!I", sceneId)])
        return self.seqNr
    def publishRenameScene(self, sceneId, name):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.name", pack("!Q", self.seqNr), pack("!I", sceneId), name.encode('utf-8')])
        return self.seqNr
    def publishReconfigScene(self, sceneId, config):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.config", pack("!Q", self.seqNr), pack("!I", sceneId), config.encode('utf-8')])
        return self.seqNr
    def publishRecolorScene(self, sceneId, color):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.color", pack("!Q", self.seqNr), pack("!I", sceneId), pack("BBB", int(color[0]*255), int(color[1]*255), int(color[2]*255))])
        return self.seqNr
    def publishVelocityScene(self, sceneId, velocity):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.velocity", pack("!Q", self.seqNr), pack("!I", sceneId), pack("!I", int(velocity*1000))])
        return self.seqNr

    def handle_snapshot(self, msg):
        """Handles a snapshot request"""
        logging.debug("Sending state snapshot request")
        identity = msg[0]
        self.snapshot.send_multipart([identity, b"mainswitch.state", pack("!Q", self.seqNr), b"\x01" if self.app.state.mainswitch else b"\x00"])
        self.snapshot.send_multipart([identity, b"brightness", pack("!Q", self.seqNr), pack("B", int(255*self.app.state.brightness))])
        for animId,  anim  in enumerate(self.app.state.animationClasses):
            self.snapshot.send_multipart([identity, b"animation.add", pack("!Q", self.seqNr), pack("!I", animId), anim.name.encode('utf-8')])
        for sceneId, scene in self.app.state.scenes.items():
            (red, green, blue) = (int(scene.color[0]*255),int(scene.color[1]*255),int(scene.color[2]*255))
            self.snapshot.send_multipart([identity, b"scene.add", pack("!Q", self.seqNr), pack("!I", sceneId), pack("!I", scene.animationId), scene.name.encode('utf-8'), pack("BBB", red, green, blue), pack("!I", int(scene.velocity * 1000)), scene.config.encode('utf-8')])
        self.snapshot.send_multipart([identity, b"scene.setactive", pack("!Q", self.seqNr), pack("!I", 0 if self.app.state.activeSceneId is None else self.app.state.activeSceneId)])


class GlinAppZmqCollector:
    def __init__(self, app, ctx, port = 6607):
        self.app = app
        self.ctx = ctx

        self.collector = self.ctx.socket(zmq.REP)
        self.collector.bind("tcp://*:" + str(port))
        self.collector = ZMQStream(self.collector)
        self.collector.on_recv(self.handle_collect)

    def handle_collect(self, msg):
        (success, seqNr, comment) = self._handle_collect(msg)
        self.collector.send_multipart([b"\x01" if success else b"\x00", pack("!I", seqNr), comment.encode("utf-8")])

    def _handle_collect(self, msg):
        """Handle incoming message"""
        try:
            if len(msg) < 1:
                err_msg = "Got empty message. Ignoring."
                logging.info(err_msg)
                return(False, 0, err_msg)
            if msg[0] == b"brightness":
                return self._handle_collect_brightness(msg)

            # "mainswitch.state" <bool>
            elif msg[0] == b"mainswitch.state":
                return self._handle_collect_mainswitch_state(msg)

            # "mainswitch.toogle"
            elif msg[0] == b"mainswitch.toggle":
                return self._handle_collect_mainswitch_toggle(msg)

            # "scene.add" <animationId> <name> <config>
            elif(msg[0] == b"scene.add"):
                return self._handle_collect_scene_add(msg)

            # "scene.config" <sceneId> <config>
            elif msg[0] == b"scene.config":
                return self._handle_collect_scene_reconfig(msg)

            elif msg[0] == b"scene.color":
                return self._handle_collect_scene_recolor(msg)

            elif msg[0] == b"scene.velocity":
                return self._handle_collect_scene_velocity(msg)

            # "scene.name" <sceneId> <name>
            elif msg[0] == b"scene.name":
                return self._handle_collect_scene_rename(msg)

            # "scene.rm" <sceneId>
            elif msg[0] == b"scene.rm":
                return self._handle_collect_scene_rm(msg)

            # "scene.setactive" <sceneId>
            elif msg[0] == b"scene.setactive":
                return self._handle_collect_scene_setactive(msg)

            else:
                logging.info("Invalid Command: {cmd}".format(cmd=(msg[0].decode('utf-8', 'replace'))))
                return (False, 0, "Invalid Command")

        except Exception as inst:
            logging.error(inst)
            raise

    def _handle_collect_brightness(self, msg):
        if len(msg) != 2:
            err_msg = "Invalid brightness message. Expected 2 frames"
            logging.info(err_msg)
            return (False, 0, )
        if len(msg[1]) != 1:
            err_msg = "Invalid brightness message. Parameter must be exactly 1 Byte"
            logging.info(err_msg)
            return(False, 0, err_msg)
        return self.app.setBrightness(msg[1][0]/255)

    def _handle_collect_mainswitch_state(self, msg):
        # "mainswitch.state" <bool>
        if len(msg) != 2:
            err_msg = "Invalid mainswitch.state message. Expected 2 frames"
            logging.info(err_msg)
            return (False, 0, err_msg)
        if len(msg[1]) != 1:
            err_msg = "Invalid mainswitch.state message. Parameter must be exactly 1 Byte"
            logging.info(err_msg)
            return (False, 0, err_msg)
        if msg[1] == b"\x00":
            return self.app.setMainSwitch(False)
        else:
            return self.app.setMainSwitch(True)

    def _handle_collect_mainswitch_toggle(self, msg):
        # "mainswitch.toggle"
        if len(msg) != 1:
            err_msg = "Invalid mainswitch.toggle message. Expected 1 frame"
            logging.info(err_msg)
            return (False, 0, err_msg)
        return self.app.toggleMainSwitch()

    def _handle_collect_scene_add(self, msg):
        # "scene.add" <animationId> <name> <color> <velocity> <config>
        if len(msg) != 5 and len(msg) != 6:
            err_msg = "Invalid scene.add message. Expected 5 or 6 frames, got " + str(len(msg))
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[1]) != 4:
            err_msg = "Invalid scene.add message. AnimationId should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[3]) != 3:
            err_msg = "Invalid scene.add message. Color should be exactly 3 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[4]) != 4:
            err_msg = "Invalid scene.add message. Color should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        (animId,) = unpack("!I", msg[1])
        color = self._parse_color(msg[3])
        (velocity,) = unpack("!I", msg[4])
        try:
            config = msg[5].decode('utf-8') if len(msg) == 6 else "" # config ist optional
            return self.app.registerScene(animId, msg[2].decode('utf-8'), color, velocity/1000, config)
        except UnicodeDecodeError:
            err_msg = "Invalid scene.add message. Contained invalid Unicode Characters."
            logging.info(err_msg)
            return(False, 0, err_msg)

    def _handle_collect_scene_recolor(self, msg):
        # "scene.config" <sceneId> <color>
        if len(msg) != 3:
            err_msg = "Invalid scene.color message. Expected 3 frames"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[1]) != 4:
            err_msg = "Invalid scene.color message. SceneId should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[2]) != 3:
            err_msg = "Invalid scene.color message. Color should be exactly 3 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        (sceneId,) = unpack("!I", msg[1])
        color = self._parse_color(msg[2])
        return self.app.recolorScene(sceneId, color)

    def _handle_collect_scene_velocity(self, msg):
        # "scene.config" <sceneId> <color>
        if len(msg) != 3:
            err_msg = "Invalid scene.velocity message. Expected 3 frames"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[1]) != 4:
            err_msg = "Invalid scene.velocity message. SceneId should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[2]) != 4:
            err_msg = "Invalid scene.velocity message. Velocity should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        (sceneId,) = unpack("!I", msg[1])
        (velocity,) = unpack("!I", msg[2])
        return self.app.velocityScene(sceneId, velocity/1000)

    def _handle_collect_scene_reconfig(self, msg):
        # "scene.config" <sceneId> <config>
        if len(msg) != 3:
            err_msg = "Invalid scene.config message. Expected 3 frames"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[1]) != 4:
            err_msg = "Invalid scene.config message. SceneId should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        (sceneId,) = unpack("!I", msg[1])
        try:
            return self.app.reconfigScene(sceneId, msg[2].decode('utf-8'))
        except UnicodeDecodeError:
            err_msg = "Invalid scene.config message. Configuration contained invalid Unicode Characters."
            logging.info(err_msg)
            return(False, 0, err_msg)


    def _handle_collect_scene_rename(self, msg):
        # "scene.name" <sceneId> <name>
        if len(msg) != 3:
            err_msg = "Invalid scene.name message. Expected 3 frames"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[1]) != 4:
            err_msg = "Invalid scene.name message. SceneId should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        (sceneId,) = unpack("!I", msg[1])
        try:
            return self.app.renameScene(sceneId, msg[2].decode('utf-8'))
        except UnicodeDecodeError:
            err_msg = "Invalid scene.name message. Name contained invalid Unicode Characters."
            logging.info(err_msg)
            return(False, 0, err_msg)

    def _handle_collect_scene_rm(self, msg):
        # "scene.rm" <sceneId>
        if len(msg) != 2:
            err_msg = "Invalid scene.rm message. Expected 2 frames"
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[1]) != 4:
            err_msg = "Invalid scene.rm message. SceneId should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        (sceneId,) = unpack("!I", msg[1])
        return self.app.removeScene(sceneId)

    def _handle_collect_scene_setactive(self, msg):
        # "scene.setactive" <sceneId>
        if len(msg) != 2:
            err_msg = "Invalid scene.setactive message. Expected 2 frames, got " + str(len(msg))
            logging.info(err_msg)
            return(False, 0, err_msg)
        if len(msg[1]) != 4:
            err_msg = "Invalid scene.setactive message. SceneId should be exactly 4 Bytes"
            logging.info(err_msg)
            return(False, 0, err_msg)
        (sceneId,) = unpack("!I", msg[1])
        return self.app.setActiveScene(sceneId)

    def _parse_color(self, msg):
        (red, green, blue,) = unpack("BBB", msg)
        color = np.array([red/255, green/255, blue/255])
        return color
