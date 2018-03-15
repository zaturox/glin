"""Main Module. Boots Glin"""

import argparse
import configparser
import logging
import os
import sys
from pkg_resources import iter_entry_points

import glin.animations
import glin.app
import glin.hardware

def boot():
    """Read configuration files, initialize glin and run main loop"""
    argparser = argparse.ArgumentParser(
        description="Controller for LED stripes (WS2801, WS2811 an similar)")
    argparser.add_argument("-c", "--config", metavar="CONFIGFILE", dest="configfiles", action='append',
                           help='Configuration File. May be repeated multiple times. Later configuration files override previous ones.')
    argparser.add_argument("-d", "--debug", dest="log_debug", action='store_const', const=True, help='Set log level to debug. Overrides -i/--info')
    argparser.add_argument("-i", "--info", dest="log_info", action='store_const', const=True, help='Set log level to info.')

    args = argparser.parse_args()

    if args.log_debug:
        logging.basicConfig(level=logging.DEBUG)
    elif args.log_info:
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
    led_count = int(cfg["core"]["leds"])
    if "hwbackend" not in cfg["core"]:
        logging.critical("No hwbackend value found in [core] section in configurations files")
        sys.exit()
    backend_name = cfg["core"]["hwbackend"]

    hwbackends = list(iter_entry_points(group='glin.hwbackend', name=backend_name))
    if len(hwbackends) != 1:
        logging.critical("Found multiple hwbackend with same name. Cant decide upon one. Quitting.")
        sys.exit()
    backend_class = hwbackends[0].load()
    backend_configuration = dict(cfg[backend_name]) if backend_name in cfg else {}
    backend = backend_class(led_count=led_count, config=backend_configuration)

    app = glin.app.GlinApp(led_count, hw_backend=backend)

    for entry_point in iter_entry_points(group='glin.animation', name=None):
        animation_class = entry_point.load()
        try:
            if issubclass(animation_class, glin.animations.AbstractAnimation):
                app.register_animation(animation_class)
            else:
                logging.error("This is not a valid animation class. Has to be subclass of glin.animations:AbstraktAnimation. Ignoring.: {ep}"
                              .format(ep=entry_point))
        except TypeError:
            logging.error("This is not a Class. Ignoring.: {ep}".format(ep=entry_point))

    app.execute()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    boot()
