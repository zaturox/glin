import numpy as np

class AbstractAnimation:
    """Base Class for animations"""
    name = "AbstractAnimation" # Animation Name presentet to UI
    def __init__(self):
        self.config = ""
        self.color = np.ones(3)
        self.velocity = 1.0
    def maxFps(self):
        """report maximum available frames per second to glin core. range [0, +infinite]"""
        return float('inf') # unlimited, use system maxFps
    @staticmethod
    def checkConfig(config):
        """Just check the given config, do not apply it. Returns true, of config is valid, otherwise false."""
        return True
    def prepare(self, numLed, targetFps):
        """setup animation"""
        self.numLed = numLed
        self.targetFps = targetFps
    def setConfig(self, config):
        self.config = config
    def setColor(self, color):
        self.color = color
    def setVelocity(self, velocity):
        self.velocity = velocity
    def nextFrame(self, buf):
        """render next frame into data buffer"""
        pass
    def finish(self):
        """Animation has stopped. Clean up."""
        pass

class StaticColorAnimation(AbstractAnimation):
    name = "Static Color" # presentet to UI
    def __init__(self):
        super().__init__()
    def maxFps(self):
        return 0
    def prepare(self, numLed, targetFps):
        super().prepare(numLed, targetFps)
    def nextFrame(self, buf):
        buf[:] = self.color

class NovaAnimation(AbstractAnimation):
    name = "Nova"
    def __init__(self):
        super().__init__()
        self.novas=[]
    def maxFps(self):
        return 30
    class Nova:
        def __init__(self, numLed):
            self.numLed = numLed
            self.color = np.array([0.5*np.random.randint(3), 0.5*np.random.randint(3), 0.5*np.random.randint(3)])
            self.center = np.random.randint(self.numLed)
            self.externalTime = 0
            self.time = 0
            self.velocity = np.random.randint(1, 4)
        def tick(self, stepsize):
            self.externalTime += stepsize
            self.time = int(self.externalTime / self.velocity)
        def writeData(self, data):
            if (self.time < 24):
                data[self.center] += (self.color / 2**(self.time / 3))
            if (self.time > 0):
                if (self.center-self.time >= -10):
                    for exp, pos in enumerate(np.arange(self.center-self.time, self.center-self.time+10 if self.center-self.time+10 < self.center else self.center)):
                        if pos >= 0:
                            data[pos] += self.color / 2**exp
                if (self.center+self.time < self.numLed + 10):
                    for exp, pos in enumerate(np.arange(self.center+self.time, self.center+self.time-10 if self.center+self.time-10 > self.center else self.center, -1)):
                        if pos < self.numLed:
                            data[pos] += self.color / 2**exp
        def dead(self):
            return self.center-self.time+10 < 0 and self.center+self.time >= self.numLed+10
    def prepare(self, numLed, targetFps):
        super().prepare(numLed, targetFps)
        self.novas=[self.Nova(self.numLed),self.Nova(self.numLed),self.Nova(self.numLed)]
    def nextFrame(self, buf):
        data = np.zeros((self.numLed,3))
        if np.random.rand() < 1/60*self.velocity:
            self.novas.append(self.Nova(self.numLed))
        for nova in self.novas:
            nova.tick(self.velocity)
            nova.writeData(data)
        buf[:,:] = np.clip(data, 0, 1)
        for nova in self.novas:
            if nova.dead():
                self.novas.remove(nova)
