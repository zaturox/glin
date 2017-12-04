from setuptools import setup


def readme():
    with open('README.rst') as f:
        return f.read()

setup(name='glin',
      version='0.0.3',
      long_description=readme(),
      description='Manages animations for LED stripes',
      url='http://github.com/zaturox/glin',
      author='zaturox',
      author_email='zaturox@noreply.github.com',
      license='LGPL',
      packages=['glin'],
      include_package_data=True,
      scripts=['bin/glin'],
      entry_points={
            "glin.animation": [
                  "Nova = glin.animations:NovaAnimation",
                  "StaticColor = glin.animations:StaticColorAnimation",
            ],
            "glin.hwbackend": [
                  "udp = glin.hwBackend:UDP",
            ],
      },
      install_requires=[
            'numpy',
            'pyzmq',
            'setuptools',
      ],
      zip_safe=False) 
