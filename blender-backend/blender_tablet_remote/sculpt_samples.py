"""Convert pointer history to spaced native brush daubs, preserving its pressure."""
import math


class BrushSamples:
    def __init__(self, spacing, aspect, pressure_size=False):
        self.spacing = max(float(spacing), 1e-6)
        self.aspect = float(aspect)
        self.pressure_size = pressure_size
        self.previous = None
        self.last_daub = None
        self.remaining = self.spacing

    def _step(self, point):
        pressure = max(.05, point['pressure']) if self.pressure_size else 1.0
        return self.spacing * pressure

    def feed(self, points, limit=4096):
        daubs = []
        for point in points:
            if self.previous is None and point['pressure'] <= 0:
                continue
            if self.previous is None:
                daubs.append(dict(point))
                self.last_daub = dict(point)
                self.remaining = self._step(point)
            else:
                start = self.previous
                distance = math.hypot((point['u']-start['u'])*self.aspect, point['v']-start['v'])
                consumed = 0.0
                while distance > 0 and distance-consumed >= self.remaining-1e-12:
                    consumed += self.remaining
                    fraction = min(1.0, consumed/distance)
                    daub = {key: start[key]+(point[key]-start[key])*fraction
                            for key in ('u','v','pressure','time')}
                    daubs.append(daub)
                    if len(daubs) > limit:
                        raise OverflowError('Brush sample limit')
                    self.last_daub = daub
                    self.remaining = self._step(daub)
                self.remaining -= max(0.0, distance-consumed)
            self.previous = dict(point)
        # The endpoint is a provisional preview. The next UPDATE replaces it;
        # it must not become another permanent daub at every network packet.
        tail = self.previous
        if tail is not None and self.last_daub is not None and all(
                abs(tail[key]-self.last_daub[key]) < 1e-10 for key in ('u','v','pressure')):
            tail = None
        return daubs, tail
