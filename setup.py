from setuptools import setup, find_packages


def readme():
    with open('README.rst') as f:
        return f.read()

setup(name='glin',
      version='0.0.4',
      long_description=readme(),
      description='Manages animations for LED stripes',
      url='http://github.com/zaturox/glin',
      author='zaturox',
      author_email='glin@zaturox.de',
      license='LGPL',
      packages=find_packages(),
      include_package_data=True,
      scripts=['bin/glin'],
      entry_points={
          "glin.animation": [
              "Nova = glin.animations:NovaAnimation",
              "StaticColor = glin.animations:StaticColorAnimation",
          ],
          "glin.hwbackend": [
              "udp = glin.hardware:UDP",
          ],
      },
      install_requires=[
          'numpy',
          'pyzmq',
          'setuptools',
      ],
      zip_safe=False)
