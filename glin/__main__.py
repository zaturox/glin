import logging
import glin.animations
import glin.app

def boot():
    app = glin.app.GlinApp(160)
    wid = app.registerAnimation(glin.animations.StaticColorAnimation)
    wid = app.registerAnimation(glin.animations.NovaAnimation)
    app.execute()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    boot()