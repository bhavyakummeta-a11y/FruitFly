"""Render the companion in a separate process so plotting cannot delay controls."""
import copy
import multiprocessing
from queue import Empty, Full


def _render(obstacles, scenery, frames, stop):
    from .view import View
    view = View(obstacles, scenery=scenery)
    try:
        while not stop.is_set():
            try:
                frame = frames.get(timeout=.1)
            except Empty:
                view.plt.pause(.01)
                if not view.plt.fignum_exists(view.fig.number):
                    break
                continue
            # Discard obsolete display frames, not aircraft telemetry.
            while True:
                try:
                    frame = frames.get_nowait()
                except Empty:
                    break
            args, kwargs = frame
            view.update(*args, **kwargs)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        view.plt.close(view.fig)


class Companion:
    def __init__(self, obstacles, scenery=False):
        ctx = multiprocessing.get_context('spawn')
        self.frames = ctx.Queue(maxsize=2)
        self.stop = ctx.Event()
        self.process = ctx.Process(target=_render,
                                   args=(obstacles, scenery, self.frames, self.stop), daemon=True)
        self.process.start()

    def update(self, *args, **kwargs):
        if self.stop.is_set() or not self.process.is_alive():
            raise RuntimeError('Companion closed or failed; stopping controller.')
        try:
            # Snapshot mutable simulator state before the queue feeder serializes it.
            self.frames.put_nowait(copy.deepcopy((args, kwargs)))
        except Full:
            pass  # Slow graphics must never stall aircraft control.

    def close(self):
        self.stop.set()
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        self.frames.cancel_join_thread()
        self.frames.close()
