"""Task-private prepared appearances on disk with one bounded process RAM cache.

No pickle, cross-task pixel identity reuse, or approximate feature recomputation.
The original matching pixels and features are restored exactly on a cache miss.
"""
from collections import OrderedDict
from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import shutil
import threading
import uuid

import cv2
import numpy as np

from .cancellation import check


class AppearanceCache:
    def __init__(self, max_bytes=256 * 1024**2):
        self.max_bytes = max_bytes
        self.bytes = 0
        self._items = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def size(value):
        return (value.image.nbytes + value.histogram.nbytes
                + (value.descriptors.nbytes if value.descriptors is not None else 0)
                + len(value.keypoints) * 128
                + sum(item.nbytes for item in value.palette.values() if isinstance(item, np.ndarray)))

    def get(self, key):
        with self._lock:
            if key not in self._items:
                return None
            value, size = self._items.pop(key)
            self._items[key] = value, size
            return value

    def put(self, key, value):
        size = self.size(value)
        with self._lock:
            previous = self._items.pop(key, None)
            if previous is not None:
                self.bytes -= previous[1]
            while self._items and self.bytes + size > self.max_bytes:
                _, (_, removed) = self._items.popitem(last=False)
                self.bytes -= removed
            if size <= self.max_bytes:
                self._items[key] = value, size
                self.bytes += size


SHARED_CACHE = AppearanceCache()


class AppearanceStorageError(RuntimeError):
    """Resource failure invalidates the batch, not just a competing picture."""


def _digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            check()
            value.update(block)
    return value.hexdigest()


class DiskAppearances(Mapping):
    def __init__(self, directory, bindings, *, cache=None):
        self.directory = Path(directory)
        self.directory.mkdir()
        self.bindings = bindings
        self.cache = cache if cache is not None else SHARED_CACHE
        self.namespace = uuid.uuid4().hex
        self._records = {}

    def __len__(self):
        return len(self._records)

    def __iter__(self):
        return iter(self._records)

    def __contains__(self, identity):
        # Membership must never decode pixels or displace the working set.
        return identity in self._records

    def __setitem__(self, identity, appearance):
        check()
        # File names are generated locally and never taken from uploaded IDs.
        path = self.directory / (uuid.uuid4().hex + '.npz')
        arrays = {'image': appearance.image, 'histogram': appearance.histogram,
                  'descriptors': appearance.descriptors if appearance.descriptors is not None else np.empty((0, 128), np.float32),
                  'has_descriptors': np.array(appearance.descriptors is not None),
                  'keypoints': np.array([(p.pt[0], p.pt[1], p.size, p.angle, p.response, p.octave, p.class_id)
                                         for p in appearance.keypoints], dtype=np.float64).reshape(-1, 7),
                  'digest': np.array(appearance.digest)}
        arrays.update({'palette_' + key: np.asarray(value) for key, value in appearance.palette.items()})
        if shutil.disk_usage(self.directory).free < sum(item.nbytes for item in arrays.values()) + 65536:
            raise AppearanceStorageError('本批预览缓存空间不足，请等待旧批次清理或分批处理。')
        try:
            with path.open('xb') as stream:
                np.savez(stream, **arrays)
            digest = _digest(path)
        except OSError:
            path.unlink(missing_ok=True)
            raise AppearanceStorageError('本批预览缓存写入失败，请检查可用空间后重新处理。') from None
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        self._records[identity] = path, digest
        self.bindings[str(path.resolve())] = digest
        self.cache.put((self.namespace, identity), appearance)

    def __getitem__(self, identity):
        check()
        path, expected = self._records[identity]
        found = self.cache.get((self.namespace, identity))
        if found is not None:
            return found
        if path.is_symlink() or _digest(path) != expected:
            raise ValueError('本批预览缓存发生变化，请重新导入。')
        from .matching import _Appearance
        with np.load(path, allow_pickle=False) as stored:
            image = stored['image']
            image.setflags(write=False)
            points = [cv2.KeyPoint(float(p[0]), float(p[1]), float(p[2]), float(p[3]),
                                  float(p[4]), int(p[5]), int(p[6])) for p in stored['keypoints']]
            palette = {key[8:]: stored[key] if stored[key].ndim else stored[key].item()
                       for key in stored.files if key.startswith('palette_')}
            value = _Appearance(image, points, stored['descriptors'] if stored['has_descriptors'].item() else None,
                                stored['histogram'], stored['digest'].item(), palette)
        self.cache.put((self.namespace, identity), value)
        return value
