# photobooth_slideshow
Lightweight opengl slideshow for your (not only) raspberry pi micro. It can be used to display on a screen/TV/beamer photos taken by a photobooth setup.

Raspberry pi micro have disappointing performance. Launching a graphical X environment is possible but very slow.

The pi3d openGL python library can be used instead to display pictures as openGL textures. The code borrows from https://github.com/pi3d/pi3d_demos (especially the Slideshow.py and PictureFrame.py examples).

The main program actively polls a directory for new images and displays them as soon as they are available. By default, the picture directory is polled every 5 seconds. When no new picture has been detected for a long time (30 seconds), the program switches to a random slideshow.

Before developping this tool, I used the viewer from my smart TV that supports DLNA but the viewer required to be restarted to take into account new images. Field tests show that the first thing people expect from a photobooth stand is that it shows the picture it has *just* taken and not some random picture taken ages ago.

## Requirements

* numpy
* pillow
* pi3d

## Installation

Standard python best practices apply here

Create a python virtual environment & activate it
```
virtualenv --python=python3 virtualenv_for_photobooth_viewer
```
Install the package
```
python setup.py install
```
## Run
```
pb-slideshow -d <path_to_your_picture_directory>
```
Command line switches:
* *-d, --directory*: directory where you store your images. If a new image is written, it will automatically be detected and displayed
* *--fps*: the number of frames per second. The default value is 15 but can be easily adjusted to fit your setup (higher values have greater cpu usage, lower values have less smooth rendering)

## Technical Considerations
* polling the directory will look like a bad idea compared to inotify but I could not find any remote file system (NFS/Samba) that has builtin support for inotify.
