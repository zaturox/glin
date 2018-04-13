"""Glin Server - Manage Animations for LED Stripes"""

import datetime
import logging
from collections import namedtuple
from types import SimpleNamespace

import numpy as np
import zmq
from zmq.eventloop.ioloop import IOLoop, PeriodicCallback
from zmq.eventloop.zmqstream import ZMQStream

import glin.zmq.messages as msgs

Scene = namedtuple('Scene', 'animation_id name color velocity config')

class GlinApp:
    """Main Class for Management"""
    def __init__(self, led_count, hw_backend, port=6606):
        self.ctx = zmq.Context()
        self.led_count = led_count
        self.port = port

        self.loop = IOLoop.instance()
        self.caller = PeriodicCallback(self._on_next_frame, 1000/30, self.loop)
        self.hw_communication = hw_backend
        self.hw_communication.connect()
        self.zmq_collector = GlinAppZmqCollector(self, self.ctx)
        self.zmq_publisher = GlinAppZmqPublisher(self, self.ctx)

        # server side configuration
        self.config = SimpleNamespace()
        self.config.max_fps = 60

        # current state (somehow client side configuration)
        self.state = SimpleNamespace()
        self.state.animationClasses = []
        self.state.activeSceneId = None
        self.state.activeAnimation = None
        self.state.scenes = {}
        self.state.brightness = 1.0
        self.state.sceneIdCtr = 0
        self.state.mainswitch = True
        self.state.target_fps = 0
        self.state.lastFrameSent = None

    def set_brightness(self, brightness):
        """set general brightness in range 0...1"""
        brightness = min([1.0, max([brightness, 0.0])]) # enforces range 0 ... 1
        self.state.brightness = brightness
        self._repeat_last_frame()
        sequence_number = self.zmq_publisher.publish_brightness(brightness)
        logging.debug("Set brightness to {brightPercent:05.1f}%".format(brightPercent=brightness*100))
        return (True, sequence_number, "OK")

    def register_animation(self, animation_class):
        """Add a new animation"""
        self.state.animationClasses.append(animation_class)
        return len(self.state.animationClasses) - 1

    def add_scene(self, animation_id, name, color, velocity, config):
        """Add a new scene, returns Scene ID"""
        # check arguments
        if animation_id < 0 or animation_id >= len(self.state.animationClasses):
            err_msg = "Requested to register scene with invalid Animation ID. Out of range."
            logging.info(err_msg)
            return(False, 0, err_msg)
        if self.state.animationClasses[animation_id].check_config(config) is False:
            err_msg = "Requested to register scene with invalid configuration."
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.sceneIdCtr += 1
        self.state.scenes[self.state.sceneIdCtr] = Scene(animation_id, name, color, velocity, config)
        sequence_number = self.zmq_publisher.publish_scene_add(self.state.sceneIdCtr, animation_id, name, color, velocity, config)
        logging.debug("Registered new scene.")

        # set this scene as active scene if none is configured yet
        if self.state.activeSceneId is None:
            self.set_scene_active(self.state.sceneIdCtr)
        return (True, sequence_number, "OK")

    def remove_scene(self, scene_id):
        """remove a scene by Scene ID"""
        if self.state.activeSceneId == scene_id:
            err_msg = "Requested to delete scene {sceneNum}, which is currently active. Cannot delete active scene.".format(sceneNum=scene_id)
            logging.info(err_msg)
            return(False, 0, err_msg)
        try:
            del self.state.scenes[scene_id]
            logging.debug("Deleted scene {sceneNum}".format(sceneNum=scene_id))
        except KeyError:
            err_msg = "Requested to delete scene {sceneNum}, which does not exist".format(sceneNum=scene_id)
            logging.info(err_msg)
            return(False, 0, err_msg)
        # if we are here, we deleted a scene, so publish it
        sequence_number = self.zmq_publisher.publish_scene_remove(scene_id)
        logging.debug("Removed scene {sceneNum}".format(sceneNum=scene_id))
        return (True, sequence_number, "OK")

    def set_scene_name(self, scene_id, name):
        """rename a scene by scene ID"""
        if not scene_id in self.state.scenes: # does that scene_id exist?
            err_msg = "Requested to rename scene {sceneNum}, which does not exist".format(sceneNum=scene_id)
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.scenes[scene_id] = self.state.scenes[scene_id]._replace(name=name) # TODO: is there a better solution?
        sequence_number = self.zmq_publisher.publish_scene_name(scene_id, name)
        logging.debug("Renamed scene {sceneNum}".format(sceneNum=scene_id))
        return (True, sequence_number, "OK")

    def set_scene_config(self, scene_id, config):
        """reconfigure a scene by scene ID"""
        if not scene_id in self.state.scenes: # does that scene_id exist?
            err_msg = "Requested to reconfigure scene {sceneNum}, which does not exist".format(sceneNum=scene_id)
            logging.info(err_msg)
            return(False, 0, err_msg)
        if scene_id == self.state.activeSceneId:
            pass  # TODO: maybe calculate next frame, esp. if static scene
        self.state.scenes[scene_id] = self.state.scenes[scene_id]._replace(config=config)
        sequence_number = self.zmq_publisher.publish_scene_config(scene_id, config)
        logging.debug("Reconfigured scene {sceneNum}".format(sceneNum=scene_id))
        return (True, sequence_number, "OK")

    def set_scene_color(self, scene_id, color):
        """reconfigure a scene by scene ID"""
        if not scene_id in self.state.scenes: # does that scene_id exist?
            err_msg = "Requested to recolor scene {sceneNum}, which does not exist".format(sceneNum=scene_id)
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.scenes[scene_id] = self.state.scenes[scene_id]._replace(color=color)
        sequence_number = self.zmq_publisher.publish_scene_color(scene_id, color)
        logging.debug("Recolored scene {sceneNum}".format(sceneNum=scene_id))
        if scene_id == self.state.activeSceneId:
            self.state.activeAnimation.set_color(color)
            self._do_next_frame() # TODO: make it more sensible, e.g. call only if static scene
        return (True, sequence_number, "OK")

    def set_scene_velocity(self, scene_id, velocity):
        """reconfigure a scene by scene ID"""
        if not scene_id in self.state.scenes: # does that scene_id exist?
            err_msg = "Requested to set velocity on scene {sceneNum}, which does not exist".format(sceneNum=scene_id)
            logging.info(err_msg)
            return(False, 0, err_msg)
        self.state.scenes[scene_id] = self.state.scenes[scene_id]._replace(velocity=velocity)
        sequence_number = self.zmq_publisher.publish_scene_velocity(scene_id, velocity)
        logging.debug("set velocity on scene {sceneNum}".format(sceneNum=scene_id))
        if scene_id == self.state.activeSceneId:
            self.state.activeAnimation.set_velocity(velocity)
            self._do_next_frame() # TODO: make it more sensible, e.g. call only if static scene
        return (True, sequence_number, "OK")

    def set_scene_active(self, scene_id):
        """sets the active scene by scene ID"""
        if self.state.activeSceneId != scene_id: # do nothing if scene has not changed
            self._deactivate_scene()
            sequence_number = self.zmq_publisher.publish_active_scene(scene_id)
            self.state.activeSceneId = scene_id
            if self.state.mainswitch is True: # activate scene only if we are switched on
                self._activate_scene()
            logging.debug("Set scene {sceneNum} as active scene".format(sceneNum=scene_id))
            return (True, sequence_number, "OK")
        else:
            logging.debug("Scene {sceneNum} already is active scene".format(sceneNum=scene_id))
            return (False, 0, "This already is the activated scene.")

    def set_mainswitch_state(self, state):
        """Turns output on or off. Also turns hardware on ir off"""
        if self.state.mainswitch == state:
            err_msg = "MainSwitch unchanged, already is {sState}".format(sState="On" if state else "Off") # fo obar lorem ipsum
            logging.debug(err_msg) # fo obar lorem ipsum
            return (False, 0, err_msg) # because nothing changed
        self.state.mainswitch = state
        sequence_number = self.zmq_publisher.publish_mainswitch_state(state)
        logging.debug("MainSwitch toggled, new state is {sState}".format(sState="On" if state else "Off")) # fo obar lorem ipsum
        if state is True:
            self.hw_communication.switch_on()
            self._activate_scene() # reinit scene
        else:
            self._deactivate_scene()
            self.hw_communication.switch_off()
        return (True, sequence_number, "OK")

    def toggle_mainswitch_state(self):
        """Toggles the mainswitch state"""
        return self.set_mainswitch_state(not self.state.mainswitch)

    def _activate_scene(self):
        if self.state.activeSceneId in self.state.scenes: # is scene_id valid? if not, assume there is no scene configured
            animation_class = self.state.animationClasses[self.state.scenes[self.state.activeSceneId].animation_id]
            self.state.activeAnimation = animation_class()
            target_fps = min(self.config.max_fps, self.state.activeAnimation.get_max_fps(), self.hw_communication.get_max_fps())
            if target_fps < 0:
                target_fps = 0
            self.state.target_fps = target_fps
            logging.debug("Running with {fps} FPS".format(fps=target_fps))
            self.state.activeAnimation.prepare(self.led_count, target_fps)
            self.state.activeAnimation.set_color(self.state.scenes[self.state.activeSceneId].color)
            self.state.activeAnimation.set_velocity(self.state.scenes[self.state.activeSceneId].velocity)
            self.state.activeAnimation.set_config(self.state.scenes[self.state.activeSceneId].config)
            if target_fps > 0:   # 0 FPS means one-shot -> no periodic callback required
                self.caller.callback_time = 1000/target_fps
                self.caller.start()
            self.loop.add_callback_from_signal(self._do_next_frame) # execute once to not have to wait for periodic callback (self.caller), esp. if 0 or low FPS
        else:
            self.state.activeAnimation = None # don't do anything. stuck with last frame.

    def _deactivate_scene(self):
        if not self.state.activeAnimation is None:
            self.caller.stop() # stop rendering new frames
            self.state.activeAnimation.finish()
            self.state.activeAnimation = None

    def _on_next_frame(self):
        logging.debug("generating next frame")
        self._do_next_frame()

    def _do_next_frame(self):
        if self.state.activeAnimation:
            buf = np.zeros((self.led_count, 3))
            self.state.activeAnimation.render_next_frame(buf)
            self.state.last_buf = np.copy(buf)
            self._send_frame(buf)
        else:
            logging.debug("app: No Active Animation")

    def _repeat_last_frame(self):
        # only do something, if there is an active animation, else output is considered to be turned off
        if hasattr(self.state, 'last_buf') and self.state.last_buf is not None and self.state.activeAnimation is not None:
            if self.state.target_fps < self.config.max_fps / 4: # to not overload hwbackend, only resend, if active animation is very slow
                self._send_frame(np.copy(self.state.last_buf))

    def _send_frame(self, buf):
        np.clip(buf, 0.0, 1.0, out=buf)
        self.state.lastFrameSent = datetime.datetime.now()
        buf *= self.state.brightness
        self.hw_communication.send(buf)

    def execute(self):
        """Execute Main Loop"""
        try:
            logging.debug("Entering IOLoop")
            self.loop.start()
            logging.debug("Leaving IOLoop")
        except KeyboardInterrupt:
            logging.debug("Leaving IOLoop by KeyboardInterrupt")
        finally:
            self.hw_communication.disconnect()


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
        self.sequence_number = 0

    def publish_brightness(self, brightness):
        """publish changed brightness"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.brightness(self.sequence_number, brightness))
        return self.sequence_number
    def publish_mainswitch_state(self, state):
        """publish changed mainswitch state"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.mainswitch_state(self.sequence_number, state))
        return self.sequence_number
    def publish_active_scene(self, scene_id):
        """publish changed active scene"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.scene_active(self.sequence_number, scene_id))
        return self.sequence_number
    def publish_scene_add(self, scene_id, animation_id, name, color, velocity, config):
        """publish added scene"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.scene_add(self.sequence_number, scene_id, animation_id, name, color, velocity, config))
        return self.sequence_number
    def publish_scene_remove(self, scene_id):
        """publish the removal of a scene"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.scene_remove(self.sequence_number, scene_id))
        return self.sequence_number
    def publish_scene_name(self, scene_id, name):
        """publish a changed scene name"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.scene_name(self.sequence_number, scene_id, name))
        return self.sequence_number
    def publish_scene_config(self, scene_id, config):
        """publish a changed scene configuration"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.scene_config(self.sequence_number, scene_id, config))
        return self.sequence_number
    def publish_scene_color(self, scene_id, color):
        """publish a changed scene color"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.scene_color(self.sequence_number, scene_id, color))
        return self.sequence_number
    def publish_scene_velocity(self, scene_id, velocity):
        """publish a changed scene velovity"""
        self.sequence_number += 1
        self.publisher.send_multipart(msgs.MessageBuilder.scene_velocity(self.sequence_number, scene_id, velocity))
        return self.sequence_number

    def handle_snapshot(self, msg):
        """Handles a snapshot request"""
        logging.debug("Sending state snapshot request")
        identity = msg[0]
        self.snapshot.send_multipart([identity] + msgs.MessageBuilder.mainswitch_state(self.sequence_number, self.app.state.mainswitch))
        self.snapshot.send_multipart([identity] + msgs.MessageBuilder.brightness(self.sequence_number, self.app.state.brightness))
        for animation_id, anim  in enumerate(self.app.state.animationClasses):
            self.snapshot.send_multipart([identity] + msgs.MessageBuilder.animation_add(self.sequence_number, animation_id, anim.name))
        for scene_id, scene in self.app.state.scenes.items():
            self.snapshot.send_multipart([identity] + msgs.MessageBuilder.scene_add(
                self.sequence_number, scene_id, scene.animation_id, scene.name, scene.color, scene.velocity, scene.config))
        self.snapshot.send_multipart([identity] + msgs.MessageBuilder.scene_active(
            self.sequence_number, 0 if self.app.state.activeSceneId is None else self.app.state.activeSceneId))


class GlinAppZmqCollector:
    """Collects ZeroMQ messages from clients"""
    def __init__(self, app, ctx, port=6607):
        self.app = app
        self.ctx = ctx

        self.collector = self.ctx.socket(zmq.REP)
        self.collector.bind("tcp://*:" + str(port))
        self.collector = ZMQStream(self.collector)
        self.collector.on_recv(self.handle_collect)

    def handle_collect(self, msg):
        """handle an incoming message"""
        (success, sequence_number, comment) = self._handle_collect(msg)
        self.collector.send_multipart(msgs.MessageWriter().bool(success).uint64(sequence_number).string(comment).get())

    def _handle_collect(self, msg):
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

            # "scene.add" <animation_id> <name> <config>
            elif msg[0] == b"scene.add":
                return self._handle_collect_scene_add(msg)

            # "scene.config" <scene_id> <config>
            elif msg[0] == b"scene.config":
                return self._handle_collect_scene_reconfig(msg)

            elif msg[0] == b"scene.color":
                return self._handle_collect_scene_recolor(msg)

            elif msg[0] == b"scene.velocity":
                return self._handle_collect_scene_velocity(msg)

            # "scene.name" <scene_id> <name>
            elif msg[0] == b"scene.name":
                return self._handle_collect_scene_rename(msg)

            # "scene.rm" <scene_id>
            elif msg[0] == b"scene.rm":
                return self._handle_collect_scene_rm(msg)

            # "scene.setactive" <scene_id>
            elif msg[0] == b"scene.setactive":
                return self._handle_collect_scene_setactive(msg)

            else:
                logging.info("Invalid Command: {cmd}".format(cmd=(msg[0].decode('utf-8', 'replace'))))
                return (False, 0, "Invalid Command")

        except Exception as inst:
            logging.error(inst)
            raise

    def _handle_collect_brightness(self, msg):
        try:
            (brightness,) = msgs.MessageParser.brightness(msg)
            return self.app.set_brightness(brightness)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_mainswitch_state(self, msg):
        # "mainswitch.state" <bool>
        try:
            (state,) = msgs.MessageParser.mainswitch_state(msg)
            return self.app.set_mainswitch_state(state)
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
        return self.app.toggle_mainswitch_state()

    def _handle_collect_scene_add(self, msg):
        # "scene.add" <animation_id> <name> <color> <velocity> <config>
        try:
            (animation_id, name, color, velocity, config) = msgs.MessageParser.scene_add(msg)
            return self.app.add_scene(animation_id, name, color, velocity, config)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_recolor(self, msg):
        # "scene.color" <scene_id> <color>
        try:
            (scene_id, color) = msgs.MessageParser.scene_color(msg)
            return self.app.set_scene_color(scene_id, color)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_velocity(self, msg):
        # "scene.velocity" <scene_id> <velocity>
        try:
            (scene_id, velocity) = msgs.MessageParser.scene_velocity(msg)
            return self.app.set_scene_velocity(scene_id, velocity)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_reconfig(self, msg):
        # "scene.config" <scene_id> <config>
        try:
            (scene_id, config) = msgs.MessageParser.scene_config(msg)
            return self.app.set_scene_config(scene_id, config)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_rename(self, msg):
        # "scene.name" <scene_id> <name>
        try:
            (scene_id, name) = msgs.MessageParser.scene_name(msg)
            return self.app.set_scene_name(scene_id, name)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_rm(self, msg):
        # "scene.rm" <scene_id>
        try:
            (scene_id,) = msgs.MessageParser.scene_remove(msg)
            return self.app.remove_scene(scene_id)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)

    def _handle_collect_scene_setactive(self, msg):
        # "scene.setactive" <scene_id>
        try:
            (scene_id,) = msgs.MessageParser.scene_active(msg)
            return self.app.set_scene_active(scene_id)
        except msgs.MessageParserError as err:
            err_msg = str(err)
            logging.info(err_msg)
            return (False, 0, err_msg)
