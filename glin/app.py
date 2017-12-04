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

Scene = namedtuple('Scene', 'animationId name config')

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
        self.zmqPublisher.publishBrightness(brightness)
        logging.debug("Set brightness to {brightPercent:05.1f}%".format(brightPercent=brightness*100))

    def registerAnimation(self, animType):
        """Add a new animation"""
        self.state.animationClasses.append(animType)
        return len(self.state.animationClasses) - 1

    def registerScene(self, animationId, sceneName, config):
        """Add a new scene, returns Scene ID"""
        # check arguments
        if animationId < 0 or animationId >= len(self.state.animationClasses):
            logging.info("Requested to register scene with invalid Animation ID. Out of range.")
            return
        if self.state.animationClasses[animationId].checkConfig(config) == False:
            logging.info("Requested to register scene with invalid configuration.")
        self.state.sceneIdCtr += 1
        self.state.scenes[self.state.sceneIdCtr] = Scene(animationId, sceneName, config)
        self.zmqPublisher.publishAddScene(self.state.sceneIdCtr, animationId, sceneName, config)
        logging.debug("Registered new scene. ID: {sceneNum}".format(sceneNum=self.state.sceneIdCtr))

        # set this scene as active scene if none is configured yet
        if self.state.activeSceneId is None:
            self.setActiveScene(self.state.sceneIdCtr)
        return self.state.sceneIdCtr

    def removeScene(self, sceneId):
        """remove a scene by Scene ID"""
        if self.state.activeSceneId == sceneId:
            logging.info("Requested to delete scene {sceneNum}, which is currently active. Cannot delete active scene.".format(sceneNum=sceneId))
            return
        try:
            del self.state.scenes[sceneId]
            logging.debug("Deleted scene {sceneNum}".format(sceneNum=sceneId))
        except KeyError:
            logging.info("Requested to delete scene {sceneNum}, which does not exist".format(sceneNum=sceneId))
            return
        # if we are here, we deleted a scene, so publish it
        self.zmqPublisher.publishRemoveScene(sceneId)
        logging.debug("Removed scene {sceneNum}".format(sceneNum=sceneId))

    def renameScene(self, sceneId, name):
        """rename a scene by scene ID"""
        if not sceneId in self.state.scenes: # does that sceneId exist?
            logging.info("Requested to rename scene {sceneNum}, which does not exist".format(sceneNum=sceneId))
            return
        self.state.scenes[sceneId] = self.state.scenes[sceneId]._replace(name=name) # TODO: is there a better solution?
        self.zmqPublisher.publishRenameScene(sceneId, name)
        logging.debug("Renamed scene {sceneNum}".format(sceneNum=sceneId))

    def reconfigScene(self, sceneId, config):
        """reconfigure a scene by scene ID"""
        if not sceneId in self.state.scenes: # does that sceneId exist?
            logging.info("Requested to reconfigure scene {sceneNum}, which does not exist".format(sceneNum=sceneId))
            return
        if sceneId == self.state.activeSceneId:
            pass  # what should i do? restart scene? ignore it?
        self.state.scenes[sceneId] = self.state.scenes[sceneId]._replace(config=config)
        self.zmqPublisher.publishReconfigScene(sceneId, config)
        logging.debug("Reconfigured scene {sceneNum}".format(sceneNum=sceneId))

    def setActiveScene(self, sceneId):
        """sets the active scene by scene ID"""
        if self.state.activeSceneId != sceneId: # do nothing if scene has not changed
            self._deactivateScene()
            self.zmqPublisher.publishActiveScene(sceneId)
            self.state.activeSceneId = sceneId
            if self.state.mainswitch is True: # activate scene only if we are switched on
                self._activateScene()
            logging.debug("Set scene {sceneNum} as active scene".format(sceneNum=sceneId))
        else:
            logging.debug("Scene {sceneNum} already is active scene".format(sceneNum=sceneId))

    def setMainSwitch(self, state):
        """Turns output on or off. Also turns hardware on ir off"""
        if self.state.mainswitch == state:
            logging.debug("MainSwitch unchanged, already is {sState}".format(sState="On" if state else "Off")) # fo obar lorem ipsum
            return  # because nothing changed
        self.state.mainswitch = state
        self.zmqPublisher.publishMainSwitch(state)
        logging.debug("MainSwitch toggled, new state is {sState}".format(sState="On" if state else "Off")) # fo obar lorem ipsum
        if state is True:
            self.hwComm.switchOn()
            self._activateScene() # reinit scene
        else:
            self._deactivateScene()
            self.hwComm.switchOff()

    def _activateScene(self):
        if self.state.activeSceneId in self.state.scenes: # is sceneId valid? if not, assume there is no scene configured
            animClass = self.state.animationClasses[self.state.scenes[self.state.activeSceneId].animationId]
            self.state.activeAnimation = animClass()
            targetFps = min( self.config.maxFps, self.state.activeAnimation.maxFps(), self.hwComm.maxFps() )
            if targetFps < 0:
                targetFps = 0
            self.state.targetFps = targetFps
            logging.debug("Running with {fps} FPS".format(fps=targetFps))
            self.state.activeAnimation.prepare(self.numLed, targetFps, self.state.scenes[self.state.activeSceneId].config)
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
        self.setMainSwitch(not self.state.mainswitch)

    def _on_nextFrame(self):
        logging.debug("generating next frame")
        self._doNextFrame()

    def _doNextFrame(self):
        if self.state.activeAnimation:
            buf = np.zeros(3*self.numLed)
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
    def publishMainSwitch(self, state):
        self.seqNr += 1
        self.publisher.send_multipart([b"mainswitch.state", pack("!Q", self.seqNr), b"\x01" if state else b"\x00"])
    def publishActiveScene(self, sceneId):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.setactive", pack("!Q", self.seqNr), pack("!I", sceneId)])
    def publishAddScene(self, sceneId, animationId, name, config):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.add", pack("!Q", self.seqNr), pack("!I", sceneId), pack("!I", animationId), name.encode('utf-8'), config.encode('utf-8')])
    def publishRemoveScene(self, sceneId):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.rm", pack("!Q", self.seqNr), pack("!I", sceneId)])
    def publishRenameScene(self, sceneId, name):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.rename", pack("!Q", self.seqNr), pack("!I", sceneId), name.encode('utf-8')])
    def publishReconfigScene(self, sceneId, config):
        self.seqNr += 1
        self.publisher.send_multipart([b"scene.reconfig", pack("!Q", self.seqNr), pack("!I", sceneId), config.encode('utf-8')])

    def handle_snapshot(self, msg):
        """Handles a snapshot request"""
        logging.debug("Sending state snapshot request")
        identity = msg[0]
        self.snapshot.send_multipart([identity, b"mainswitch.state", pack("!Q", self.seqNr), b"\x01" if self.app.state.mainswitch else b"\x00"])
        self.snapshot.send_multipart([identity, b"brightness", pack("!Q", self.seqNr), pack("B", int(255*self.app.state.brightness))])
        for animId,  anim  in enumerate(self.app.state.animationClasses):
            self.snapshot.send_multipart([identity, b"animation.add", pack("!Q", self.seqNr), pack("!I", animId), anim.name.encode('utf-8')])
        for sceneId, scene in self.app.state.scenes.items():
            self.snapshot.send_multipart([identity, b"scene.add", pack("!Q", self.seqNr), pack("!I", sceneId), pack("!I", scene.animationId), scene.name.encode('utf-8'), scene.config.encode('utf-8')])
        self.snapshot.send_multipart([identity, b"scene.setactive", pack("!Q", self.seqNr), pack("!I", 0 if self.app.state.activeSceneId is None else self.app.state.activeSceneId)])


class GlinAppZmqCollector:
    def __init__(self, app, ctx, port = 6607):
        self.app = app
        self.ctx = ctx

        self.collector = self.ctx.socket(zmq.PULL)
        self.collector.bind("tcp://*:" + str(port))
        self.collector = ZMQStream(self.collector)
        self.collector.on_recv(self.handle_collect)

    def handle_collect(self, msg):
        """Handle incoming message"""
        try:
            if len(msg) < 1:
                logging.info("Got empty message. Ignoring.")
                return
            if msg[0] == b"brightness":
                self._handle_collect_brightness(msg)

            # "mainswitch.state" <bool>
            elif msg[0] == b"mainswitch.state":
                self._handle_collect_mainswitch_state(msg)

            # "mainswitch.toogle"
            elif msg[0] == b"mainswitch.toggle":
                self._handle_collect_mainswitch_toggle(msg)

            # "scene.add" <animationId> <name> <config>
            elif(msg[0] == b"scene.add"):
                self._handle_collect_scene_add(msg)

            # "scene.reconfig" <sceneId> <config>
            elif msg[0] == b"scene.reconfig":
                self._handle_collect_scene_reconfig(msg)

            # "scene.rename" <sceneId> <name>
            elif msg[0] == b"scene.rename":
                self._handle_collect_scene_rename(msg)

            # "scene.rm" <sceneId>
            elif msg[0] == b"scene.rm":
                self._handle_collect_scene_rm(msg)

            # "scene.setactive" <sceneId>
            elif msg[0] == b"scene.setactive":
                self._handle_collect_scene_setactive(msg)

            else:
                logging.info("Invalid Command: {cmd}".format(cmd=(msg[0].decode('utf-8', 'replace'))))

        except Exception as inst:
            logging.error(inst)
            raise

    def _handle_collect_brightness(self, msg):
        if len(msg) != 2:
            logging.info("Invalid brightness message. Expected 2 frames")
            return
        if len(msg[1]) != 1:
            logging.info("Invalid brightness message. Parameter must be exactly 1 Byte")
            return
        self.app.setBrightness(msg[1][0]/255)

    def _handle_collect_mainswitch_state(self, msg):
        # "mainswitch.state" <bool>
        if len(msg) != 2:
            logging.info("Invalid mainswitch.state message. Expected 2 frames")
            return
        if len(msg[1]) != 1:
            logging.info("Invalid mainswitch.state message. Parameter must be exactly 1 Byte")
            return
        if msg[1] == b"\x00":
            self.app.setMainSwitch(False)
        else:
            self.app.setMainSwitch(True)

    def _handle_collect_mainswitch_toggle(self, msg):
        # "mainswitch.toggle"
        if len(msg) != 1:
            logging.info("Invalid mainswitch.toggle message. Expected 1 frame")
            return
        self.app.toggleMainSwitch()

    def _handle_collect_scene_add(self, msg):
        # "scene.add" <animationId> <name> <config>
        if len(msg) != 4:
            logging.info("Invalid scene.add message. Expected 4 frames, got " + str(len(msg)))
            return
        if len(msg[1]) != 4:
            logging.info("Invalid scene.add message. AnimationId should be exactly 4 Bytes")
            return
        (animId,) = unpack("!I", msg[1])
        try:
            self.app.registerScene(animId, msg[2].decode('utf-8'), msg[3].decode('utf-8'))
        except UnicodeDecodeError:
            logging.info("Invalid scene.add message. Contained invalid Unicode Characters.")

    def _handle_collect_scene_reconfig(self, msg):
        # "scene.reconfig" <sceneId> <config>
        if len(msg) != 3:
            logging.info("Invalid scene.reconfig message. Expected 3 frames")
            return
        if len(msg[1]) != 4:
            logging.info("Invalid scene.reconfig message. SceneId should be exactly 4 Bytes")
            return
        (sceneId,) = unpack("!I", msg[1])
        try:
            self.app.reconfigScene(sceneId, msg[2].decode('utf-8'))
        except UnicodeDecodeError:
            logging.info("Invalid scene.reconfig message. Configuration contained invalid Unicode Characters.")


    def _handle_collect_scene_rename(self, msg):
        # "scene.rename" <sceneId> <name>
        if len(msg) != 3:
            logging.info("Invalid scene.rename message. Expected 3 frames")
            return
        if len(msg[1]) != 4:
            logging.info("Invalid scene.rename message. SceneId should be exactly 4 Bytes")
            return
        (sceneId,) = unpack("!I", msg[1])
        try:
            self.app.renameScene(sceneId, msg[2].decode('utf-8'))
        except UnicodeDecodeError:
            logging.info("Invalid scene.rename message. Name contained invalid Unicode Characters.")

    def _handle_collect_scene_rm(self, msg):
        # "scene.rm" <sceneId>
        if len(msg) != 2:
            logging.info("Invalid scene.rm message. Expected 2 frames")
            return
        if len(msg[1]) != 4:
            logging.info("Invalid scene.rm message. SceneId should be exactly 4 Bytes")
            return
        (sceneId,) = unpack("!I", msg[1])
        self.app.removeScene(sceneId)

    def _handle_collect_scene_setactive(self, msg):
        # "scene.setactive" <sceneId>
        if len(msg) != 2:
            logging.info("Invalid scene.setactive message. Expected 2 frames, got " + str(len(msg)))
            return
        if len(msg[1]) != 4:
            logging.info("Invalid scene.setactive message. SceneId should be exactly 4 Bytes")
            return
        (sceneId,) = unpack("!I", msg[1])
        self.app.setActiveScene(sceneId)
