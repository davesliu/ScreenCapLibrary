import threading
import time

from .client import Client, run_in_background
from .utils import _norm_path, suppress_stderr
from mss import mss
from robot.utils import get_link_path, is_truthy, PY2
from robot.api import logger
from PIL import Image

try:
    import cv2
    import numpy as np
except ImportError:
    raise ImportError('Importing cv2 failed. Make sure you have opencv-python installed.')

try:
    from gtk import gdk
except ImportError:
    gdk = None

try:
    from gi import require_version
    require_version('Gdk', '3.0')
    from gi.repository import Gdk
except ImportError:
    Gdk = None


class VideoClient(Client):

    def __init__(self, screenshot_module, screenshot_directory, fps):
        Client.__init__(self)
        self.screenshot_module = screenshot_module
        self._given_screenshot_dir = _norm_path(screenshot_directory)
        self._stop_condition = threading.Event()
        self.alias = None
        try:
            self.fps = int(fps)
        except ValueError:
            raise ValueError('The fps argument must be of type integer.')

    def start_video_recording(self, alias, name, size_percentage, embed, embed_width):
        self.alias = alias
        self.name = name
        self.embed = embed
        self.embed_width = embed_width
        self.path = self._save_screenshot_path(basename=self.name, format='webm')
        self.futures = self.capture_screen(self.path, self.fps, size_percentage=size_percentage)
        self.clear_thread_queues()

    def stop_video_recording(self):
        self._stop_thread()
        if is_truthy(self.embed):
            self._embed_video(self.path, self.embed_width)
        return self.path

    def capture_screen(self, path, fps, size_percentage):
        if self.screenshot_module and self.screenshot_module.lower() == 'pygtk':
            return self._record_gtk(path, fps, size_percentage, stop=self._stop_condition)
        else:
            return self._record_mss(path, fps, size_percentage)

    @run_in_background
    def _record_mss(self, path, fps, size_percentage):
        fourcc = cv2.VideoWriter_fourcc(*'VP08')
        with mss() as sct:
            if not sct.grab(sct.monitors[1]):
                raise Exception('Monitor not available.')
            width = int(sct.grab(sct.monitors[1]).width * size_percentage)
            height = int(sct.grab(sct.monitors[1]).height * size_percentage)
        with suppress_stderr():
            vid = cv2.VideoWriter('%s' % path, fourcc, fps, (width, height))
        while not self._stop_condition.isSet():
            with mss() as sct:
                sct_img = sct.grab(sct.monitors[1])
            numpy_array = np.array(sct_img)
            resized_array = cv2.resize(numpy_array, dsize=(width, height), interpolation=cv2.INTER_AREA) \
                if size_percentage != 1 else numpy_array
            frame = cv2.cvtColor(resized_array, cv2.COLOR_RGBA2RGB)
            vid.write(frame)
        vid.release()
        cv2.destroyAllWindows()

    def _record_gtk(self, path, fps, size_percentage, stop):
        if not gdk and not Gdk:
            raise RuntimeError('PyGTK not installed/supported on this platform.')
        if PY2:
            return self._record_gtk_py2(path, fps, size_percentage, stop)
        else:
            return self._record_gtk_py3(path, fps, size_percentage, stop)

    @run_in_background
    def _record_gtk_py2(self, path, fps, size_percentage, stop):
        window = gdk.get_default_root_window()
        if not window:
            raise Exception('Monitor not available.')
        fourcc = cv2.VideoWriter_fourcc(*'VP08')
        width, height = window.get_size()
        resized_width = int(width * size_percentage)
        resized_height = int(height * size_percentage)
        with suppress_stderr():
            vid = cv2.VideoWriter('%s' % path, fourcc, fps, (resized_width, resized_height))
        while not stop.isSet():
            pb = gdk.Pixbuf(gdk.COLORSPACE_RGB, False, 8, width, height)
            pb = pb.get_from_drawable(window, window.get_colormap(),
                                      0, 0, 0, 0, width, height)
            numpy_array = pb.get_pixels_array()
            resized_array = cv2.resize(numpy_array, dsize=(resized_width, resized_height), interpolation=cv2.INTER_AREA) \
                if size_percentage != 1 else numpy_array
            frame = cv2.cvtColor(resized_array, cv2.COLOR_RGB2BGR)
            vid.write(frame)
        vid.release()
        cv2.destroyAllWindows()

    @run_in_background
    def _record_gtk_py3(self, path, fps, size_percentage, stop):
        window = Gdk.get_default_root_window()
        if not window:
            raise Exception('Monitor not available.')
        fourcc = cv2.VideoWriter_fourcc(*'VP08')
        width = window.get_width()
        height = window.get_height()
        resized_width = int(width * size_percentage)
        resized_height = int(height * size_percentage)
        with suppress_stderr():
            vid = cv2.VideoWriter('%s' % path, fourcc, fps, (resized_width, resized_height))
        while not stop.isSet():
            time.sleep(0.001)
            # pb = Gdk.pixbuf_get_from_window(window, 0, 0, width, height)
            # numpy_array = np.array(Image.frombytes("RGB", (width, height), pb.get_pixels()))
            # resized_array = cv2.resize(numpy_array, dsize=(resized_width, resized_height), interpolation=cv2.INTER_AREA) \
            #     if size_percentage != 1 else numpy_array
            # frame = cv2.cvtColor(resized_array, cv2.COLOR_RGB2BGR)
            # vid.write(frame)
        vid.release()
        cv2.destroyAllWindows()

    def _embed_video(self, path, width):
        link = get_link_path(path, self._log_dir)
        logger.info('<a href="%s"><video width="%s" autoplay><source src="%s" type="video/webm"></video></a>' %
                    (link, width, link), html=True)
