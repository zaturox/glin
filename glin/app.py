"""Glin Server - Manage Animations for LED Stripes"""

import logging
from types import SimpleNamespace
from collections import namedtuple
Scene = namedtuple('Scene', 'animationId name config')

import numpy as np

from struct import pack, unpack
import zmq
from zmq.eventloop.ioloop import IOLoop, PeriodicCallback
from zmq.eventloop.zmqstream import ZMQStream

class GlinApp:
    def __init__(self, numLed, hwBackend, port=6606):
        self.ctx = zmq.Context()
        self.numLed = numLed
        self.port = port

        self.loop = IOLoop.instance()
        self.caller = PeriodicCallback(self.on_nextFrame, 1000/30, self.loop)
        self.hwComm = hwBackend
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
        self.state.sceneIdCtr = 0
        self.state.brightness = 1.0
        self.state.mainswitch = True

    def setBrightness(self, brightness):
        brightness = min([1.0, max([brightness, 0.0])]) # enforces range 0 ... 1
        self.state.brightness = brightness
        self.zmqPublisher.publishBrightness(brightness)
    def registerAnimation(self, animType):
        self.state.animationClasses.append(animType)
        return len(self.state.animationClasses) - 1

    def registerScene(self, animationId, sceneName, config):
        # check arguments
        if animationId < 0 or animationId >= len(self.state.animationClasses):
            logging.info("Requested to register scene with invalid Animation ID. Out of range.")
            return
        if self.state.animationClasses[animationId].checkConfig(config) == False:
            logging.info("Requested to register scene with invalid configuration.")
        self.state.sceneIdCtr += 1
        self.state.scenes[self.state.sceneIdCtr] = Scene(animationId, sceneName, config)
        self.zmqPublisher.publishAddScene(self.state.sceneIdCtr, animationId, sceneName, config)
        # set this scene as active scene if none is configured yet
        if self.state.activeSceneId is None:
            self.setActiveScene(self.state.sceneIdCtr)
        return self.state.sceneIdCtr

    def removeScene(self, sceneId):
        if self.state.activeSceneId == sceneId:
            logging.info("Requested to delete scene {sceneNum}, which is currently active. Cannot delete active scene.".format(sceneNum=sceneId))
            return
        try:
            del self.state.scenes[sceneId]
        except KeyError:
            logging.info("Requested to delete scene {sceneNum}, which does not exist".format(sceneNum=sceneId))
            return
        # if we are here, we deleted a scene, so publish it
        self.zmqPublisher.publishRemoveScene(sceneId)

    def renameScene(self, sceneId, name):
        if not sceneId in self.state.scenes: # does that sceneId exist?
            logging.info("Requested to rename scene {sceneNum}, which does not exist".format(sceneNum=sceneId))
            return
        self.state.scenes[sceneId] = self.state.scenes[sceneId]._replace(name=name) # TODO: shouldn't do it, its a dirty hack
        self.zmqPublisher.publishRenameScene(sceneId, name)

    def reconfigScene(self, sceneId, config):
        if not sceneId in self.state.scenes: # does that sceneId exist?
            logging.info("Requested to reconfigure scene {sceneNum}, which does not exist".format(sceneNum=sceneId))
            return
        if sceneId == self.state.activeSceneId:
            pass  # what should i do? restart scene? ignore it?
        self.state.scenes[sceneId].config = config
        self.zmqPublisher.publishReconfigScene(sceneId, config)

    def setActiveScene(self, sceneId):
        if self.state.activeSceneId != sceneId: # do nothing if scene has not changed
            self._deactivateScene()
            self.zmqPublisher.publishActiveScene(sceneId)
            self.state.activeSceneId = sceneId
            if (self.state.mainswitch == True): # activate scene only if we are switched on
                self._activateScene()

    def setMainSwitch(self, state):
        if self.state.mainswitch == state:
            return  # because nothing changed
        self.state.mainswitch = state
        self.zmqPublisher.publishMainSwitch(state)
        if state == True:
            self.hwComm.switchOn()
            self._activateScene() # reinit scene
        else:
            self._deactivateScene()
            self.hwComm.switchOff()

    def _activateScene(self):
        if self.state.activeSceneId in self.state.scenes: # is sceneId valid? if not, assume there is no scene configured
            animClass = self.state.animationClasses[self.state.scenes[self.state.activeSceneId].animationId]
            self.state.activeAnimation = animClass()
            targetFps = min(self.config.maxFps, self.state.activeAnimation.maxFps)
            if targetFps < 0:
                targetFps = 0
            logging.debug("Running with {fps} FPS".format(fps=targetFps))
            self.state.activeAnimation.prepare(self.numLed, targetFps,self.state.scenes[self.state.activeSceneId].config) 
            if targetFps > 0:   # 0 FPS means one-shot -> no periodic callback required
                self.caller.callback_time = 1000/targetFps
                self.caller.start()
            self.loop.add_callback_from_signal(self.doNextFrame) # execute once to not have to wait for periodic callback (self.caller), esp. if 0 or low FPS
        else:
            self.state.activeAnimation = None # don't do anything. stuck with last frame. 

    def _deactivateScene(self):
        if not(self.state.activeAnimation is None):
            self.caller.stop() # stop rendering new frames
            self.state.activeAnimation.finish()
            self.state.activeAnimation = None

    def toggleMainSwitch(self):
        self.setMainSwitch(not(self.state.mainswitch))

    def on_nextFrame(self):
        logging.debug("ioloop: next frame")
        self.doNextFrame()

    def doNextFrame(self):
        if self.state.activeAnimation:
            buf = np.zeros(3*self.numLed)
            self.state.activeAnimation.nextFrame(buf)
            np.clip(buf, 0.0, 1.0, out=buf)
            buf *= self.state.brightness
            self.hwComm.send(buf)
        else:
            logging.debug("app: No Active Animation")

    def execute(self):
        #self.caller.start()
        try:
            logging.debug("Entering IOLoop")
            self.loop.start()
            logging.debug("Leaving IOLoop")
        except KeyboardInterrupt:
            logging.debug("Leaving IOLoop")


class GlinAppZmqPublisher:
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
        logging.debug("Got state snapshot request")
        identity = msg[0]
        self.snapshot.send_multipart([identity, b"mainswitch.state", pack("!Q", self.seqNr), b"\x01" if self.app.state.mainswitch else b"\x00"])
        self.snapshot.send_multipart([identity, b"brightness", pack("!Q", self.seqNr), pack("B", int(255*self.app.state.brightness))])
        for animId,  anim  in enumerate(self.app.state.animationClasses):
            self.snapshot.send_multipart([identity, b"animation.add", pack("!Q", self.seqNr), pack("!I", animId), anim.name.encode('utf-8')])
        for sceneId, scene in self.app.state.scenes.items():
            self.snapshot.send_multipart([identity, b"scene.add", pack("!Q", self.seqNr), pack("!I", sceneId), pack("!I", scene.animationId), scene.name.encode('utf-8'), scene.config.encode('utf-8')])
        self.snapshot.send_multipart([identity, b"scene.setactive", pack("!Q", self.seqNr), pack("!I", 0 if self.app.state.activeSceneId is None else self.app.state.activeSceneId)])
        logging.debug("sent state")


class GlinAppZmqCollector:
    def __init__(self, app, ctx, port = 6607):
        self.app = app
        self.ctx = ctx

        self.collector = self.ctx.socket(zmq.PULL)
        self.collector.bind("tcp://*:" + str(port))
        self.collector = ZMQStream(self.collector)
        self.collector.on_recv(self.handle_collect)

    def handle_collect(self, msg):
        try:
            if len(msg) < 1:
                logging.info("Got empty message. Ignoring.")
                return
            if msg[0] == b"brightness":
                if len(msg) != 2:
                    logging.info("Invalid brightness message. Expected 2 frames")
                    return
                if(len(msg[1]) != 1):
                    logging.info("Invalid brightness message. Parameter must be exactly 1 Byte")
                    return
                self.app.setBrightness(msg[1][0]/255)

            # "mainswitch.state" <bool>
            elif(msg[0] == b"mainswitch.state"):
                if(len(msg) != 2):
                    logging.info("Invalid mainswitch.state message. Expected 2 frames")
                    return
                if(len(msg[1]) != 1):
                    logging.info("Invalid mainswitch.state message. Parameter must be exactly 1 Byte")
                    return
                if(msg[1] == b"\x00"):
                    self.app.setMainSwitch(False)
                else:
                    self.app.setMainSwitch(True)
                logging.debug("Valid mainswitch state update message. new state = "+str(msg[1]) != b"\x00")

            # "mainswitch.toogle"
            elif(msg[0] == b"mainswitch.toggle"):
                if len(msg) != 1:
                    logging.info("Invalid mainswitch.toggle message. Expected 1 frame")
                self.app.toggleMainSwitch()

            # "scene.add" <animationId> <name> <config>
            elif(msg[0] == b"scene.add"):
                if len(msg) != 4:
                    logging.info("Invalid scene.add message. Expected 4 frames, got " + str(len(msg)))
                    return
                if len(msg[1]) != 4:
                    logging.info("Invalid scene.add message. AnimationId should be exactly 4 Bytes")
                    return
                (animId,) = unpack("!I", msg[1])
                self.app.registerScene(animId, msg[2].decode('utf-8'), msg[3].decode('utf-8'))

            # "scene.reconfig" <sceneId> <config>
            elif msg[0] == b"scene.reconfig":
                if len(msg) != 3:
                    logging.info("Invalid scene.reconfig message. Expected 3 frames")
                    return
                if len(msg[1]) != 4:
                    logging.info("Invalid scene.reconfig message. SceneId should be exactly 4 Bytes")
                    return
                (sceneId,) = unpack("!I", msg[1])
                self.app.reconfigScene(sceneId, msg[2].decode('utf-8'))

            # "scene.rename" <sceneId> <name>
            elif msg[0] == b"scene.rename":
                if len(msg) != 3:
                    logging.info("Invalid scene.rename message. Expected 3 frames")
                    return
                if len(msg[1]) != 4:
                    logging.info("Invalid scene.rename message. SceneId should be exactly 4 Bytes")
                    return
                (sceneId,) = unpack("!I", msg[1])
                self.app.renameScene(sceneId, msg[2].decode('utf-8'))

            # "scene.rm" <sceneId>
            elif msg[0] == b"scene.rm":
                if len(msg) != 2:
                    logging.info("Invalid scene.rm message. Expected 2 frames")
                    return
                if len(msg[1]) != 4:
                    logging.info("Invalid scene.rm message. SceneId should be exactly 4 Bytes")
                    return
                (sceneId,) = unpack("!I", msg[1])
                self.app.removeScene(sceneId)

            # "scene.setactive" <sceneId>
            elif(msg[0] == b"scene.setactive"):
                if len(msg) != 2:
                    logging.info("Invalid scene.setactive message. Expected 2 frames, got " + str(len(msg)))
                    return
                if len(msg[1]) != 4:
                    logging.info("Invalid scene.setactive message. SceneId should be exactly 4 Bytes")
                    return
                (sceneId,) = unpack("!I", msg[1])
                self.app.setActiveScene(sceneId)

            else:
                logging.info("Invalid Command: " + msg[0])


        except Exception as inst:
            logging.error(inst)
            raise