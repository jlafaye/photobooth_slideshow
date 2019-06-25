from PIL import Image
import pi3d
import os
import datetime as dt
import imghdr
import random
import sys
from queue import Empty, Queue
from time import sleep
from threading import Thread
import argparse

import logging
logging.basicConfig(level=logging.INFO)

# whether to anti-alias map screen pixels to image pixels
# set False if no scaling required (faster, less memory needed)
MIPMAP = True
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


class Slide(pi3d.Sprite):
    def __init__(self):
        super(Slide, self).__init__(w=1.0, h=1.0)


class SlideFactory:

    def __init__(self, width, height):
        self._shader = pi3d.Shader('uv_flat')
        self._height = height
        self._width = width

    def create(self, image):
        tex = pi3d.Texture(image,
                           blend=True,
                           mipmap=MIPMAP)
        slide = Slide()
        xrat = self._width/tex.ix
        yrat = self._height/tex.iy
        if yrat < xrat:
            xrat = yrat
        wi, hi = tex.ix * xrat, tex.iy * xrat
        slide.set_draw_details(self._shader, [tex])
        slide.scale(wi, hi, 1.0)
        return slide


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

    def __init__(self, directory, grace_period, long_grace_period):
        self._directory = directory
        self._filenames = []
        self._added_files = []
        self._max_ctime = None
        self._last_update = None
        self._grace_period = grace_period
        self._long_grace_period = long_grace_period
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


def run_sampler(config, queue):

    sampler = FileSampler(config.directory,
                          dt.timedelta(0, config.timeout),
                          dt.timedelta(0, config.shot_timeout))

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
    DISPLAY = pi3d.Display.create(background=(0.0, 0.0, 0.0, 1.0),
                                  frames_per_second=config.fps)
    CAMERA = pi3d.Camera(is_3d=False)

    CAMERA = pi3d.Camera.instance()
    CAMERA.was_moved = False  # to save a tiny bit of work each loop

    logging.info('Using display of size {}x{}'.format(DISPLAY.width,
                                                      DISPLAY.height))

    factory = SlideFactory(DISPLAY.width, DISPLAY.height)

    fade = 0.0
    fade_step = 1.0 / (config.fps * FADE_TM)

    slide_background = factory.create(DEFAULT_IMAGE)
    slide_foreground = slide_background

    while DISPLAY.loop_running():
        try:
            # do we have a new picture to display ?
            image = queue.get(block=False)
            slide_background = slide_foreground
            slide_foreground = factory.create(image)
            slide_background.positionZ(-0.1)
            slide_foreground.positionZ(+0.1)
            fade = 0.0
        except Empty:
            pass

        if fade < 1.0:
            fade += fade_step
            if fade > 1.0:
                fade = 1.0

        if slide_foreground == slide_background:
            slide_foreground.set_alpha(1)
        else:
            slide_foreground.set_alpha(fade)
            slide_background.set_alpha(1-fade)

        slide_foreground.draw()
        slide_background.draw()


def run_slideshow():

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--directory', help='Image directory')
    parser.add_argument('--fps', type=int, default=20,
                        help='Number of frames for opengl loop')
    parser.add_argument('--timeout', type=int, default=5,
                        help='Time in seconds between two pictures'
                             'in random slideshow mode')
    parser.add_argument('--shot-timeout', type=int, default=30,
                        help='Number of seconds a recently shot picture'
                             'is kept on the screen before switching to'
                             'random slideshow')
    config = parser.parse_args()

    directory = config.directory
    if config.directory is None:
        logging.error('No image directory, use either -d or --directory')
        sys.exit(1)

    q = Queue()
    t = Thread(target=run_sampler,
               args=(config, q,))
    t.start()

    run_opengl(config, q)
