glin
====

**Manages animations for LED stripes**


About
-----

glin manages und runs your animations for LED stripes like WS2801, WS2811 and similar.

glin is fully implemented in Python. It uses ZeroMQ as frontend, so it's possible to use nearly every platform to build graphical or command line interfaces to interact with glin.

**glin is in active development. Consider it as unstable!**

features:
 * fully controllable via ZeroMQ
 * variable FPS, depending on animation and LED stripe capabilities
 * multiple ZeroMQ clients can be connected at the same time
 * talk to LED Strip via UDP
 * some sample animations (Static Color and Nova)
 * automatically detect and load supported animations
 
partial implemented:
 * use configuration files for server side configuration
 * load various backends for communicating with LED stripe (UDP, SPI,...)

planned features:
 * SPI backend, esp. for Raspberry Pi
 * more animations
 
dependencies:
 * Python 3 (Python 2 is not supported)
 * ZeroMQ (pyzmq)
 * Numpy
 * setuptools

 
Setup
-----
install
 * using git:
     1. clone this repository
     2. cd into the project folder
     3. run ``sudo pip install .`` or ``sudo pip install -e .``
 * using PyPI:
     ``sudo pip install glin``
 
run with ``glin``

Parameters
----------
 * ``-c``, ``--config``: specify configuration file. A example configuration file is included (example.conf)
 * ``-h``, ``--help``: show help
 
License
-------

licensed under LGPL v3.0 (see LICENSE file)
