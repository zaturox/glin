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

import glin.zmq.messages as msgs

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
        self.publisher.send_multipart(msgs.MessageBuilder.brightness(self.seqNr, brightness))
        return self.seqNr
    def publishMainSwitch(self, state):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.mainswitch(self.seqNr, state))
        return self.seqNr
    def publishActiveScene(self, sceneId):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.sceneActive(self.seqNr, sceneId))
        return self.seqNr
    def publishAddScene(self, sceneId, animationId, name, color, velocity, config):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.sceneAdd(self.seqNr, sceneId, animationId, name, color, velocity, config))
        return self.seqNr
    def publishRemoveScene(self, sceneId):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.sceneRemove(self.seqNr, sceneId))
        return self.seqNr
    def publishRenameScene(self, sceneId, name):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.sceneName(self.seqNr, sceneId, name))
        return self.seqNr
    def publishReconfigScene(self, sceneId, config):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.sceneConfig(self.seqNr, sceneId, config))
        return self.seqNr
    def publishRecolorScene(self, sceneId, color):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.sceneColor(self.seqNr, sceneId, color))
        return self.seqNr
    def publishVelocityScene(self, sceneId, velocity):
        self.seqNr += 1
        self.publisher.send_multipart(msgs.MessageBuilder.sceneVelocity(self.seqNr, sceneId, velocity))
        return self.seqNr

    def handle_snapshot(self, msg):
        """Handles a snapshot request"""
        logging.debug("Sending state snapshot request")
        identity = msg[0]
        self.snapshot.send_multipart([identity] + msgs.MessageBuilder.mainswitch(self.seqNr, self.app.state.mainswitch))
        self.snapshot.send_multipart([identity] + msgs.MessageBuilder.brightness(self.seqNr, self.app.state.brightness))
        for animId, anim  in enumerate(self.app.state.animationClasses):
            self.snapshot.send_multipart([identity] + msgs.MessageBuilder.animationAdd(self.seqNr, animId, anim.name))
        for sceneId, scene in self.app.state.scenes.items():
            self.snapshot.send_multipart([identity] + msgs.MessageBuilder.sceneAdd(self.seqNr, sceneId, scene.animationId, scene.name, scene.color, scene.velocity, scene.config))
        self.snapshot.send_multipart([identity] + msgs.MessageBuilder.sceneActive(self.seqNr, 0 if self.app.state.activeSceneId is None else self.app.state.activeSceneId))


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
        self.collector.send_multipart(msgs.MessageWriter().bool(success).uint64(seqNr).string(comment).get())

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
        try:
            (state,) = msgs.MessageParser.mainswitch(msg)
            return self.app.setMainSwitch(state)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_mainswitch_toggle(self, msg):
        # "mainswitch.toggle"
        if len(msg) != 1:
            err_msg = "Invalid mainswitch.toggle message. Expected 1 frame"
            logging.info(err_msg)
            return (False, 0, err_msg)
        return self.app.toggleMainSwitch()

    def _handle_collect_scene_add(self, msg):
        # "scene.add" <animationId> <name> <color> <velocity> <config>
        try:
            (animId, name, color, velocity, config) = msgs.MessageParser.sceneAdd(msg)
            return self.app.registerScene(animId, name, color, velocity, config)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_recolor(self, msg):
        # "scene.color" <sceneId> <color>
        try:
            (sceneId, color) = msgs.MessageParser.sceneColor(msg)
            return self.app.recolorScene(sceneId, color)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_velocity(self, msg):
        # "scene.velocity" <sceneId> <velocity>
        try:
            (sceneId, velocity) = msgs.MessageParser.sceneVelocity(msg)
            return self.app.velocityScene(sceneId, velocity)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_reconfig(self, msg):
        # "scene.config" <sceneId> <config>
        try:
            (sceneId, config) = msgs.MessageParser.sceneConfig(msg)
            return self.app.reconfigScene(sceneId, config)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_rename(self, msg):
        # "scene.name" <sceneId> <name>
        try:
            (sceneId, name) = msgs.MessageParser.sceneName(msg)
            return self.app.renameScene(sceneId, name)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_rm(self, msg):
        # "scene.rm" <sceneId>
        try:
            (sceneId,) = msgs.MessageParser.sceneRemove(msg)
            return self.app.removeScene(sceneId)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_setactive(self, msg):
        # "scene.setactive" <sceneId>
        try:
            (sceneId,) = msgs.MessageParser.sceneSetactive(msg)
            return self.app.setActiveScene(sceneId)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)
