import cv2
import numpy as np
import pytest

from hsd_tool.appearance_cache import AppearanceCache, DiskAppearances
from hsd_tool.matching import _appearance, _features, _texture


def test_bounded_shared_cache_restores_exact_pixels_features_and_decisions(tmp_path):
    rng = np.random.default_rng(42)
    image = rng.integers(0, 256, (120, 210, 3), dtype=np.uint8)
    appearance = _appearance(image, cv2.SIFT_create())
    cache = AppearanceCache(max_bytes=1)
    bindings = {}
    store = DiskAppearances(tmp_path / 'cache', bindings, cache=cache)
    store['synthetic'] = appearance
    restored = store['synthetic']
    assert cache.bytes == 0 and len(store) == 1 and len(bindings) == 1
    np.testing.assert_array_equal(restored.image, appearance.image)
    np.testing.assert_array_equal(restored.histogram, appearance.histogram)
    np.testing.assert_array_equal(restored.descriptors, appearance.descriptors)
    assert [(p.pt, p.size, p.angle, p.response, p.octave, p.class_id) for p in restored.keypoints] == [
        (p.pt, p.size, p.angle, p.response, p.octave, p.class_id) for p in appearance.keypoints]
    assert restored.digest == appearance.digest and not restored.image.flags.writeable
    for key in appearance.palette:
        np.testing.assert_array_equal(restored.palette[key], appearance.palette[key])
    assert _features(appearance, restored) == _features(appearance, appearance)
    assert _texture(appearance, restored) == _texture(appearance, appearance)


def test_same_ids_in_different_tasks_never_share_cached_images(tmp_path):
    cache = AppearanceCache(max_bytes=50000)
    stores = [DiskAppearances(tmp_path / str(i), {}, cache=cache) for i in range(2)]
    for index, store in enumerate(stores):
        for number in range(10):
            pixels = np.full((40, 60, 3), index * 100 + number, dtype=np.uint8)
            store[str(number)] = _appearance(pixels, cv2.SIFT_create())
            assert cache.bytes <= cache.max_bytes
    assert stores[0]['0'].image[0, 0, 0] == 0
    assert stores[1]['0'].image[0, 0, 0] == 100
    assert cache.bytes <= cache.max_bytes


def test_changed_disk_cache_is_rejected_instead_of_using_new_pixels(tmp_path):
    store = DiskAppearances(tmp_path / 'cache', {}, cache=AppearanceCache(max_bytes=1))
    store['x'] = _appearance(np.full((20, 30, 3), 120, np.uint8), cv2.SIFT_create())
    next((tmp_path / 'cache').glob('*.npz')).write_bytes(b'changed')
    with pytest.raises(ValueError, match='缓存发生变化'):
        store['x']


def test_cache_capacity_failure_aborts_batch_instead_of_removing_rival(tmp_path, monkeypatch):
    from PIL import Image
    from hsd_tool.appearance_cache import AppearanceStorageError
    import hsd_tool.matching as matching
    image = tmp_path / 'synthetic.png'
    Image.new('RGB', (80, 30), 'blue').save(image)
    record = {'id': 'f0001', 'issue': '', 'preview_path': str(image)}
    monkeypatch.setattr(matching, '_collect', lambda *args: [record])
    monkeypatch.setattr(matching, '_render', lambda *args: None)
    def fail(*args):
        raise AppearanceStorageError('synthetic capacity failure')
    monkeypatch.setattr(DiskAppearances, '__setitem__', fail)
    with pytest.raises(AppearanceStorageError):
        matching.prepare_matching(str(tmp_path), [], str(tmp_path / 'work'))
