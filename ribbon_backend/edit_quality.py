"""Bounded technical checks for a completed image edit, never semantic approval.

Resize alone, invisible RGB and one-level raster noise are not useful edits.
The check deliberately permits local detail changes and does not score beauty,
identity, text correctness or print readiness. No check calls another model.
"""
from contextlib import closing
import math

import numpy as np
from PIL import Image, ImageFilter

from .imaging import memory_bounded_operation, read_image


def _sample(image, size):
    with image.resize(size, Image.Resampling.LANCZOS) as reduced:
        # Hidden colour values must never constitute a visible edit. Inspect
        # both mattes so a white design is still visible to the comparator.
        result = []
        for colour in ('black', 'white'):
            with Image.new('RGBA', size, colour) as matte:
                matte.alpha_composite(reduced)
                with matte.convert('RGB') as rgb, rgb.filter(ImageFilter.GaussianBlur(.6)) as blurred:
                    result.append(np.asarray(blurred, dtype=np.int16).copy())
        return result


def _difference(first, second):
    return np.maximum(np.max(np.abs(first[0] - second[0]), axis=2),
                      np.max(np.abs(first[1] - second[1]), axis=2))


def _long_edge(size, limit):
    scale = min(1., limit / max(size))
    return tuple(max(1, round(side * scale)) for side in size)


def _new_border_cut(before, after):
    """Only flag strong new contact on a previously safely padded alpha side."""
    with before.getchannel('A') as alpha:
        if alpha.getextrema()[0] == 255:
            return False
    size = (256, 256)
    with before.getchannel('A') as a, after.getchannel('A') as b, a.resize(size) as aa, b.resize(size) as bb:
        old, new = np.asarray(aa), np.asarray(bb)
    # A four-pixel (~1.5%) clear margin is considered intentional safe padding.
    bands = ((old[:4], new[:1]), (old[-4:], new[-1:]),
             (old[:, :4], new[:, :1]), (old[:, -4:], new[:, -1:]))
    return any(not np.any(a >= 32) and np.count_nonzero(b >= 128) >= 6 for a, b in bands)


@memory_bounded_operation
def validate_edit_result(source, output, *, target):
    from .providers import ProviderError
    from hsd_tool.provider_diagnostics import diagnostic

    def reject(message):
        raise ProviderError(message, details=diagnostic('invalid_result', 'validation'))

    with closing(read_image(source)) as before, closing(read_image(output)) as after:
        # The provider validates its native requested dimensions separately.
        # This bounded projection compares the same canvas proportions rather
        # than mistaking native upscaling for a new design.
        # Fine localized texture may vanish from a coarse projection. Inspect
        # up to 512px as well, preserving canvas aspect. Compare against both
        # the original and a resize-only baseline so interpolation ringing is
        # not falsely counted as useful detail. This extra raster is bounded
        # to 2048px/4MP, rather than allocating another 40MP decoded image.
        sizes = [_long_edge(after.size, 128), _long_edge(after.size, 512)]
        baseline_size = _long_edge(after.size, 2048)
        reports = []
        with before.resize(baseline_size, Image.Resampling.LANCZOS) as baseline:
            for size in sizes:
                actual = _sample(after, size)
                delta = np.minimum(_difference(_sample(before, size), actual),
                                   _difference(_sample(baseline, size), actual))
                changed = int(np.count_nonzero(delta >= 8))
                reports.append(dict(size=list(size), changed=changed, pixels=int(delta.size)))
        if not any(r['changed'] >= max(4, math.ceil(r['pixels'] * .00025)) for r in reports):
            reject('精修结果没有足够的可见变化，原版本保留，未扣精修次数；请说明更具体的修改。')
        if target in ('asset', 'pattern') and _new_border_cut(before, after):
            reject('精修结果新增了明显的画面贴边，主体可能被截断；原版本保留，未扣精修次数。')
        return dict(verification_scope='technical_visible_change_and_new_alpha_edge_contact',
                    changed_sample_pixels=max(r['changed'] for r in reports), sample_pixels=max(r['pixels'] for r in reports),
                    projections=reports,
                    semantic_verified=False, production_verified=False)
