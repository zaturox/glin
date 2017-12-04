import numpy as np

class AbstractAnimation:
    """Base Class for animations"""
    name = "AbstractAnimation" # Animation Name presentet to UI
    def __init__(self):
        pass
    def maxFps(self):
        """report maximum available frames per second to glin core"""
        return float('inf') # unlimited, use system maxFps
    @staticmethod
    def checkConfig(config):
        """Just check the given config, do not apply it. Report result to glin core."""
        return True
    def prepare(self, numLed, targetFps, config):
        """setup animation"""
        self.numLed = numLed
        self.targetFps = targetFps
        self.config = config
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
        self.red = 1.0
        self.green = 1.0
        self.blue = 1.0
    def maxFps(self):
        return 0
    def prepare(self, numLed, targetFps, config):
        super().prepare(numLed, targetFps, config)
        import json
        try:
            cfg = json.loads(config)
            self.red = cfg["red"]
            self.green = cfg["green"]
            self.blue = cfg["blue"]
        except:
            self.red = 1.0
            self.green = 1.0
            self.blue = 1.0

    def nextFrame(self, buf):
        buf[0::3] = np.ones(self.numLed) * self.red
        buf[1::3] = np.ones(self.numLed) * self.green
        buf[2::3] = np.ones(self.numLed) * self.blue

class NovaAnimation(AbstractAnimation):
    name = "Nova"
    def __init__(self):
        super().__init__()
    def maxFps(self):
        return 30
    class Nova:
        def __init__(self, numLed):
            self.numLed = numLed
            self.color = np.array([127*np.random.randint(3), 127*np.random.randint(3), 127*np.random.randint(3)])
            self.center = np.random.randint(self.numLed)
            self.externalTime = -1
            self.time = 0
            self.velocity = np.random.randint(1, 4)
        def tick(self):
            self.externalTime += 1
            self.time = self.externalTime // self.velocity
        def writeData(self, data):
            if (self.time < 24):
                data[self.center] += (self.color // 2**(self.time / 3)).astype(np.int64)
            if (self.time > 0):
                if (self.center-self.time >= -10):
                    for exp, pos in enumerate(np.arange(self.center-self.time, self.center-self.time+10 if self.center-self.time+10 < self.center else self.center)):
                        if pos >= 0:
                            data[pos] += self.color // 2**exp
                if (self.center+self.time < self.numLed + 10):
                    for exp, pos in enumerate(np.arange(self.center+self.time, self.center+self.time-10 if self.center+self.time-10 > self.center else self.center, -1)):
                        if pos < self.numLed:
                            data[pos] += self.color // 2**exp
        def dead(self):
            return self.center-self.time+10 < 0 and self.center+self.time >= self.numLed+10
    def __init__(self):
        self.novas=[]
    def prepare(self, numLed, targetFps, config):
        super().prepare(numLed, targetFps, config)
        self.novas=[self.Nova(self.numLed),self.Nova(self.numLed),self.Nova(self.numLed)]
    def nextFrame(self, buf):
        data = np.zeros((self.numLed,3), dtype=np.int64)
        for nova in self.novas:
            nova.tick()
            nova.writeData(data)
        buf[0:] = np.clip(data, 0, 255).astype(np.float64).flatten()/255
        for nova in self.novas:
            if nova.dead():
                self.novas.remove(nova)
        if np.random.randint(60) == 0:
            self.novas.append(self.Nova(self.numLed))
