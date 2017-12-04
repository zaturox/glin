import argparse
import configparser
import logging
import os
import sys

import glin.animations
import glin.app
import glin.hwBackend

from pkg_resources import iter_entry_points

def boot():
    argparser = argparse.ArgumentParser(
        description="Controller for LED stripes (WS2801, WS2811 an similar)")
    argparser.add_argument("-c", "--config", metavar="CONFIGFILE", dest="configfiles", action='append', help='Configuration File. May be repeated multiple times. Later configuration files override previous ones.')
    argparser.add_argument("-d", "--debug", dest="log_debug", action='store_const', const=True, help='Set log level to debug. Overrides -i/--info')
    argparser.add_argument("-i", "--info",  dest="log_info",  action='store_const', const=True, help='Set log level to info.')

    args = argparser.parse_args()

    if(args.log_debug):
        logging.basicConfig(level=logging.DEBUG)
    elif(args.log_info):
        logging.basicConfig(level=logging.INFO)

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
    if "hwbackend" not in cfg["core"]:
        logging.critical("No hwbackend value found in [core] section in configurations files")
        sys.exit()
    backend_name = cfg["core"]["hwbackend"]

    hwbackends = list(iter_entry_points(group='glin.hwbackend', name=backend_name))
    if len(hwbackends) != 1:
        logging.critical("Found multiple hwbackend with same name. Cant decide upon one. Quitting.")
        sys.exit()
    Backend = hwbackends[0].load()
    backendCfg = dict(cfg[backend_name]) if backend_name in cfg else {}
    backend = Backend(numLed = numLed, config = backendCfg)

    app = glin.app.GlinApp(numLed, hwBackend = backend)

    for entry_point in iter_entry_points(group='glin.animation', name=None):
        animClass = entry_point.load()
        try:
            if issubclass(animClass, glin.animations.AbstractAnimation):
                app.registerAnimation(animClass)
            else:
                logging.error("This is not a valid animation class. Has to be subclass of glin.animations:AbstraktAnimation. Ignoring.: {ep}".format(ep=entry_point))
        except TypeError:
            logging.error("This is not a Class. Ignoring.: {ep}".format(ep=entry_point))

    app.execute()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    boot()
