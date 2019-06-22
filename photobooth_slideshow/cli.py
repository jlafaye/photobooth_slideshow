from PIL import Image
import pi3d
import os
import datetime as dt
import imghdr
import random
import sys
from queue import Empty
from time import sleep
from multiprocessing import Queue, Process
import argparse

import logging
logging.basicConfig(level=logging.DEBUG)

# whether to anti-alias map screen pixels to image pixels
# set False if no scaling required (faster, less memory needed)
MIPMAP = False
FADE_TM = 2.0


def lookup_assets():
    alternatives = ['assets', os.path.join(sys.exec_prefix, 'assets')]
    for alternative in alternatives:
        alternative = os.path.abspath(alternative)
        logging.debug('Looking up assets in {}'.format(alternative))
        if os.path.isdir(alternative):
            return alternative
    return None


ASSETS_DIR = lookup_assets()
if ASSETS_DIR is None:
    raise FileNotFoundError('Unable to find assets')
logging.debug('Found assets {}'.format(ASSETS_DIR))
DEFAULT_IMAGE = os.path.join(ASSETS_DIR, 'images', 'no_image.png')
DEFAULT_SHADER = os.path.join(ASSETS_DIR, 'shaders', 'blend_bump')


class Slide(object):
    def __init__(self):
        self.tex = None
        self.dimensions = None


def create_slide(image, width, height):
    print('image:', image)
    tex = pi3d.Texture(image,
                       blend=True,
                       mipmap=MIPMAP,
                       m_repeat=False)
    slide = Slide()
    xrat = width/tex.ix
    yrat = height/tex.iy
    if yrat < xrat:
        xrat = yrat
    print('width:', width, 'height:', height)
    print('xrat:', xrat, 'yrat:', yrat)
    print('tex.ix:', tex.ix, 'tex.iy', tex.iy)
    wi, hi = tex.ix * xrat, tex.iy * xrat
    xi = (width - wi)/2
    yi = (height - hi)/2
    slide.tex = tex
    slide.dimensions = (wi, hi, xi, yi)
    return slide


def create_slide_from_filename(filename, width, height):
    image = Image.open(filename)
    return create_slide(image, width, height)


class ImageFilter:

    def __init__(self):
        self._map = {}

    def is_image(self, filename):
        if filename not in self._map:
            what = imghdr.what(filename)
            if what:
                is_image = True
            else:
                is_image = False
            self._map[filename] = is_image
        return self._map[filename]


class FileSampler:

    def __init__(self, directory):
        self._directory = directory
        self._filenames = []
        self._added_files = []
        self._max_ctime = None
        self._last_update = None
        self._grace_period = dt.timedelta(0, 5)
        self._long_grace_period = dt.timedelta(0, 30)
        self._is_added_file = False
        self._filter = ImageFilter()

        # refresh the list of filenames
        self.list()

        # and disarm displaying added files
        # because all existing files on startup
        # will be listed as new
        self._added_files = []

    def list(self):
        filenames = []
        added_files = []
        ctimes = []
        for root, dirs, files in os.walk(self._directory):
            for name in files:
                filename = os.path.join(root, name)
                if self._filter.is_image(filename):
                    filenames.append(filename)
                    ctime = os.stat(filename).st_ctime
                    if self._max_ctime is None or ctime > self._max_ctime:
                        ctimes.append(ctime)
                        added_files.append(filename)

        self._max_ctime = max(ctimes) if ctimes else self._max_ctime
        self._added_files += added_files
        self._filenames = filenames

    def get_filename(self):
        now = dt.datetime.utcnow()
        if self._last_update is not None \
                and now-self._last_update <= self._grace_period:
            return None

        # refresh the list of files
        self.list()

        if self._added_files:
            filename = self._added_files[0]
            self._added_files = self._added_files[1:]
            self._last_update = now
            self._is_added_file = True
            return filename

        # if the current file being displayed is an 'added file'
        # we keep it on screen for at most a duration of 'long_grace_period'
        if self._is_added_file \
                and now-self._last_update <= self._long_grace_period:
            return None

        if self._filenames:
            self._last_update = now
            self._is_added_file = False
            return random.sample(self._filenames, 1)[0]

        return None


def run_sampler(directory, queue):

    sampler = FileSampler(directory)

    while True:
        filename = sampler.get_filename()
        if filename is not None:
            logging.info('Loading {}'.format(filename))
            image = Image.open(filename)
            image.load()
            queue.put(image)
        sleep(1)


def run_opengl(config, queue):

    logging.info('Starting opengl UI loop')
    # 1440x1080
    DISPLAY = pi3d.Display.create(background=(0.3, 0.3, 0.3, 1.0),
                                  # w=1440, h=1080,
                                  frames_per_second=config.fps, tk=False)

    logging.info('Using display of size {}x{}'.format(DISPLAY.width,
                                                      DISPLAY.height))

    fade = 0.0
    fade_step = 1.0 / (config.fps * FADE_TM)
    slide_foreground = None
    slide_background = create_slide_from_filename(DEFAULT_IMAGE,
                                                  DISPLAY.width,
                                                  DISPLAY.height)

    shader = pi3d.Shader('shaders/blend_bump')

    canvas = pi3d.Canvas()
    canvas.set_shader(shader)

    slide_foreground = slide_background

    while DISPLAY.loop_running():
        try:
            # do we have a new picture to display
            image = queue.get(block=False)
            slide_foreground = slide_background
            slide_background = create_slide(image,
                                            DISPLAY.width,
                                            DISPLAY.height)
            fade = 0.0
        except Empty:
            pass

        # reset two textures
        canvas.set_draw_details(canvas.shader, [slide_foreground.tex,
                                                slide_background.tex])

        # print('slide_baclgrond:', slide_background)
        # print("dimensions:", slide_background.dimensions)

        canvas.set_2d_size(slide_background.dimensions[0],
                           slide_background.dimensions[1],
                           slide_background.dimensions[2],
                           slide_background.dimensions[3])

        # need to pass shader dimensions for both textures
        canvas.unif[48:54] = canvas.unif[42:48]

        canvas.set_2d_size(slide_foreground.dimensions[0],
                           slide_foreground.dimensions[1],
                           slide_foreground.dimensions[2],
                           slide_foreground.dimensions[3])

        if fade < 1.0:
            fade += fade_step  # increment fade
            if fade > 1.0:  # more efficient to test here than in pixel shader
                fade = 1.0
            canvas.unif[44] = fade  # pass value to shader using unif list

        canvas.draw()  # then draw it


def run_slideshow():

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--directory', help='Image directory')
    parser.add_argument('--fps', type=int, default=20,
                        help='Number of frames for opengl loop')
    args = parser.parse_args()

    directory = args.directory
    if args.directory is None:
        logging.error('No image directory, use either -d or --directory')
        sys.exit(1)

    q = Queue()
    p = Process(target=run_sampler,
                args=(directory, q,))
    p.start()

    run_opengl(args, q)
