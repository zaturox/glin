"""Contains some example animations"""

import numpy as np

class AbstractAnimation:
    """Base Class for animations"""
    name = "AbstractAnimation" # Animation Name presentet to UI
    def __init__(self):
        self.config = ""
        self.color = np.ones(3)
        self.velocity = 1.0
    def get_max_fps(self):
        """report maximum available frames per second to glin core. range [0, +infinite]"""
        return float('inf') # unlimited, use system maxFps
    @staticmethod
    def check_config(config):
        """Just check the given config, do not apply it. Returns true, of config is valid, otherwise false."""
        return True
    def prepare(self, led_count, target_fps):
        """setup animation"""
        self.led_count = led_count
        self.target_fps = target_fps
    def set_config(self, config):
        """Sets scenes custom configuration"""
        self.config = config
    def set_color(self, color):
        """Sets scene color"""
        self.color = color
    def set_velocity(self, velocity):
        """Sets scene velocity"""
        self.velocity = velocity
    def render_next_frame(self, buf):
        """render next frame into data buffer"""
        pass
    def finish(self):
        """Animation has stopped. Clean up."""
        pass

class StaticColorAnimation(AbstractAnimation):
    """An animation showing a static color"""
    name = "Static Color" # presentet to UI
    def __init__(self):
        super().__init__()
    def get_max_fps(self):
        return 0
    def prepare(self, led_count, target_fps):
        super().prepare(led_count, target_fps)
    def render_next_frame(self, buf):
        buf[:] = self.color

class NovaAnimation(AbstractAnimation):
    """An animations inspired by novas"""
    name = "Nova"
    def __init__(self):
        super().__init__()
        self.novas = []
    def get_max_fps(self):
        return 30
    class Nova:
        """A single Nova"""
        def __init__(self, led_count):
            self.led_count = led_count
            self.color = np.array([0.5*np.random.randint(3), 0.5*np.random.randint(3), 0.5*np.random.randint(3)])
            self.center = np.random.randint(self.led_count)
            self.external_time = 0
            self.time = 0
            self.velocity = np.random.randint(1, 4)
        def tick(self, stepsize):
            """Go forward in time"""
            self.external_time += stepsize
            self.time = int(self.external_time / self.velocity)
        def write_data(self, data):
            """write this Novas frame LED data to buffer"""
            if self.time < 24:
                data[self.center] += (self.color / 2**(self.time / 3))
            if self.time > 0:
                if self.center-self.time >= -10:
                    for exp, pos in enumerate(np.arange(self.center-self.time,
                                                        self.center-self.time+10 if self.center-self.time+10 < self.center else self.center)):
                        if pos >= 0:
                            data[pos] += self.color / 2**exp
                if self.center+self.time < self.led_count + 10:
                    for exp, pos in enumerate(np.arange(self.center+self.time,
                                                        self.center+self.time-10 if self.center+self.time-10 > self.center else self.center, -1)):
                        if pos < self.led_count:
                            data[pos] += self.color / 2**exp
        def dead(self):
            """determine wheather this Nova is finished. This is when all parts of the animation left the viewport"""
            return self.center-self.time+10 < 0 and self.center+self.time >= self.led_count+10
    def prepare(self, led_count, target_fps):
        super().prepare(led_count, target_fps)
        self.novas = [self.Nova(self.led_count), self.Nova(self.led_count), self.Nova(self.led_count)]
    def render_next_frame(self, buf):
        data = np.zeros((self.led_count, 3))
        if np.random.rand() < 1/60*self.velocity:
            self.novas.append(self.Nova(self.led_count))
        for nova in self.novas:
            nova.tick(self.velocity)
            nova.write_data(data)
        buf[:, :] = np.clip(data, 0, 1)
        for nova in self.novas:
            if nova.dead():
                self.novas.remove(nova)
