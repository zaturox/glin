import argparse
import configparser
import logging
import os
import sys

import glin.animations
import glin.app
import glin.hwBackend


def boot():
    argparser = argparse.ArgumentParser(
        description="Controller for LED stripes (WS2801, WS2811 an similar)")
    argparser.add_argument("-c", "--config", metavar="CONFIGFILE", dest="configfiles", action='append', help='Configuration File. May be repeated multiple times. Later configuration files override previous ones.')
    args = argparser.parse_args()

    cfg = configparser.ConfigParser()
    cfgpath = os.path.join(os.path.dirname(__file__), "default.conf")
    cfg.read(cfgpath)
    if args.configfiles is not None:
        cfg.read(args.configfiles)
    
    if "core" not in cfg:
        logging.critical("No [core] section found in configurations files")
        sys.exit()
    if "leds" not in cfg["core"]:
        logging.critical("No leds value found in [core] section in configurations files")
        sys.exit()
    
    numLed = int(cfg["core"]["leds"])

    Backend = glin.hwBackend.UDP
    backendCfg = dict(cfg[Backend.EXT_NAME]) if Backend.EXT_NAME in cfg else {}
    backend = Backend(numLed = numLed, config = backendCfg)

    app = glin.app.GlinApp(numLed, hwBackend = backend)
    app.registerAnimation(glin.animations.StaticColorAnimation)
    app.registerAnimation(glin.animations.NovaAnimation)
    app.execute()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    boot()
