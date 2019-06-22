#!/usr/bin/env python

from distutils.core import setup


setup(name='photobooth_slideshow',
      version='1.0',
      description='A basic picture viewer powered by OpenGL designed for raspberry Pi',
      author='Julien Lafaye',
      author_email='jlafaye@gmail.com',
      packages=['photobooth_slideshow'],
      entry_points={
      	'console_scripts': ['pb-slideshow=photobooth_slideshow.cli:run_slideshow']
      },
      install_requires=['pillow', 'pi3d', 'numpy'],
      data_files=[('share/photobooth_slideshow/assets', ['assets/images/no_image.png',
                                                         'assets/shaders/blend_bump.vs',
                                                         'assets/shaders/blend_bump.fs'])]
)
