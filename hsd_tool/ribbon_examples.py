"""Read-only layout teaching examples, separate from production assets.

Company previews live in the instance settings directory, never in public Git
or a release archive. Only the individually reviewed bytes below are served;
neither an employee request nor a catalog entry can choose a filesystem path.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat


# width, height, byte length, SHA-256 of the authorized library preview.
# This exact allowlist is intentionally not a general image/file browser.
IMAGE_SPECS = {'HSD51441': (1200, 244, 93220, 'a2b5153296e3a54fac67be456da972a71896881193a81f06296beb73c987c3dd'),
 'HSD68622': (1200, 251, 55212, '1e0be2c47ef0c53e442e7c957fe9602a3fa04aa4a48ddf271d1965edac8381de'),
 'HSD31620': (1200, 176, 51488, '8db0283b90a0358827a08e2b74b96630300ec42ff12969dbc333ede035732c77'),
 'HSD67527': (1200, 243, 85433, '89c8ac404ee33beaaf76672c5b3aa2f46f3b6d2d2dbc1e7acb80f8fd5f2eab65'),
 'HSD68618': (1200, 251, 90998, '60e1d29fd827478af2a61c173fd8cec15fc6cdff46a7b20a84176a13b0c9df16'),
 'HSD51045': (1200, 110, 19396, 'cef44c35fea1e9dec0a3a271fe5de0a4b246004eec0730480372f398ec23f10a'),
 'HSD68027': (1200, 111, 56522, 'bc38e7fa2a299bd13f5fc4c6315e8addd641e9d13a7fb449a2f0f0f68e09052f'),
 'HSD68402': (1200, 244, 77350, 'd9c296bc1444d2320b894d54b8c0fb211676010e46ec7713ade4da5247bed5f4'),
 'HSD67181': (1200, 111, 32165, '44933fc2058fc57c05f71a046b9a7c644bded50958849122085c9f1e20115421'),
 'HSD68145': (1200, 244, 122858, '58b022aa9aa86734a7bbedcd4e72a8179cfd50d35a43fb422299b28e75d5a270'),
 'HSD53659': (1200, 252, 60561, 'd63b31765e4bcc149e4bad2c721eb2bfe5a2724cf63a91daf78b1b14839bd2ae'),
 'HSD31412': (1200, 173, 53989, 'b8baac6e353edf88bc2eb8ff487b1f828fecf74ed5f346fa64c5c994711daeb1'),
 'HSD31296': (1200, 175, 70142, '8b3fad84bc49ba2a79e592085599649e0423529d87cc24d9fca374a840fcecb4')}

EXAMPLES = ({'code': 'HSD68145',
  'title': '整齐行列排列',
  'description': '彩色方块按行列整齐重复，上下位置对齐。',
  'look_for': '重点看方块的对齐关系；中间花带属于额外装饰。',
  'mode_tags': ['grid'],
  'reference_only': False},
 {'code': 'HSD31620',
  'title': '多行错位排列',
  'description': '小图案排成三行，中间一行向旁边错开约半格。',
  'look_for': '上下行不完全对齐；本例背景简单，位置差别清楚。',
  'mode_tags': ['stagger'],
  'reference_only': False},
 {'code': 'HSD67527',
  'title': '多角度散点满铺',
  'description': '铅笔以不同角度分布，再用星星、圆点和曲线填补空隙。',
  'look_for': '主体有不同朝向；整体看似散布，仍有重复组合。',
  'mode_tags': ['scatter'],
  'reference_only': False},
 {'code': 'HSD51441',
  'title': '单个主题重复',
  'description': '同一组花束沿长度方向重复，大小和间距基本一致。',
  'look_for': '先组成一个完整主题，再重复摆放。',
  'mode_tags': ['single'],
  'reference_only': False},
 {'code': 'HSD68622',
  'title': '多个主题轮换',
  'description': '书本、铅笔、电脑等不同图案，按固定顺序依次排开。',
  'look_for': '不同图案依次出现；一轮结束后再从头重复。',
  'mode_tags': ['single'],
  'reference_only': False},
 {'code': 'HSD51045',
  'title': '两端定位主图',
  'description': '两端各放一个固定主图，中间用横线和大块留空连接。',
  'look_for': '主图位置固定在两端；中间不需要继续铺满大图。',
  'mode_tags': ['ends', 'ends_open'],
  'reference_only': False},
 {'code': 'HSD68027',
  'title': '左右分区',
  'description': '左半边是绿白斜条，右半边是密集小图，分界很明确。',
  'look_for': '同一幅里使用两种不同底纹；还可以叠加端部主图。',
  'mode_tags': ['panels', 'split'],
  'reference_only': False},
 {'code': 'HSD68618',
  'title': '组合场景循环',
  'description': '房屋、树木、雪人和背景组成一个场景，整组沿长度方向重复。',
  'look_for': '人物和背景一起重复，与单个图案轮换不同。',
  'mode_tags': ['scene'],
  'reference_only': False},
 {'code': 'HSD68402',
  'title': '上下边饰',
  'description': '上下使用粉色心形边条，中间安排主要图案。',
  'look_for': '边条与中间主题分别控制；边饰也能搭配其他排法。',
  'mode_tags': ['bordered'],
  'reference_only': False},
 {'code': 'HSD67181',
  'title': '整幅固定造型',
  'description': '笔尖、分段笔身和橡皮组成完整造型，有固定的起点与终点。',
  'look_for': '需要保留整幅结构，不把整支铅笔反复平铺。',
  'mode_tags': ['fullwidth'],
  'reference_only': False},
 {'code': 'HSD53659',
  'title': '大小主体轮换',
  'description': '较大的半身人物与较小的全身人物交替出现，小配饰填在空隙中。',
  'look_for': '重点看主体一大一小的节奏，不只是换成不同人物。',
  'mode_tags': ['alternating'],
  'reference_only': False},
 {'code': 'HSD31412',
  'title': '上下两区组合',
  'description': '上半是豹纹，下半是黄白条纹，两区大致各占一半。',
  'look_for': '这是上下两块大区域，不是上下两条窄边饰。',
  'mode_tags': ['stacked'],
  'reference_only': False},
 {'code': 'HSD31296',
  'title': '相邻主体正倒交替',
  'description': '正立人物与倒置人物沿长度方向轮换，再重复同一组。',
  'look_for': '相邻主体旋转180度；不是左右镜像，也不是上下两排。',
  'mode_tags': ['opposed'],
  'reference_only': False})

MODE_GUIDES = (
    dict(mode='grid', name='整齐平铺', summary='图案按行列整齐重复。',
         note='案例重点看方块对齐，中间花带是额外装饰；实际行数、间距以当前模板和预览为准。',
         example_ids=['HSD68145']),
    dict(mode='stagger', name='错位平铺', summary='相邻两行错开约半格。',
         note='对照上下行的位置差别，图案和底纹仍使用你自己选择的素材。',
         example_ids=['HSD31620']),
    dict(mode='scatter', name='随机散点', summary='图案的位置和角度有小范围变化。',
         note='当前模板做小范围错动和旋转；案例中的小配饰需由所选图案或底图提供。',
         example_ids=['HSD67527']),
    dict(mode='single', name='单排重复', summary='沿中线排一行，可重复同一图案，也可让多个图案依次轮换。',
         note='选一个图案时重复同一图案，选多个时依次排列。',
         example_ids=['HSD51441', 'HSD68622']),
    dict(mode='ends', name='两端主图', summary='两端放大主图，中间排列较小图案。',
         note='案例主要说明两端定位；当前模板中间还会有小图，留白和方向以实际预览为准。',
         example_ids=['HSD51045']),
    dict(mode='panels', name='分区拼接', summary='按左、中、右三段安排不同密度和大小的图案。',
         note='案例是两段分区的对照，当前模板按三段生成，不会自动复制案例的底纹和分界。',
         example_ids=['HSD68027']),
    dict(mode='bordered', name='上下边饰', summary='上下放窄边饰，中间重复主体图案。',
         note='至少选两张：第一张是中间主体，其余用于上下边饰。案例中的独立底纹不会自动生成。',
         example_ids=['HSD68402']),
    dict(mode='scene', name='组合循环', summary='先组成一组高低错落的图案，再整组重复。',
         note='选多图时按顺序组成高低组合；要保留原场景内部关系，请上传一张完整组合图。不会自动重建建筑或背景。',
         example_ids=['HSD68618']),
    dict(mode='fullwidth', name='整幅定位', summary='一张完整设计保持比例放入画幅，不循环平铺。',
         note='仅选一张完整设计。默认完整居中、不拉伸；比例不同时会留白。不会把独立人物自动拼成铅笔外形，重复间距不适用。',
         example_ids=['HSD67181']),
    dict(mode='alternating', name='大小交替', summary='所选图案按一大一小的节奏依次重复。',
         note='按选择顺序轮换大小，人物内容不会改画；半身、全身和小配饰需要使用自己准备的图案。',
         example_ids=['HSD53659']),
    dict(mode='ends_open', name='两端留白', summary='两端放主图，中间只保留所选底图。',
         note='选一张时两端使用同一图，选两张时分别用于左端和右端。中间不再铺小图，也不自动生成横线；重复间距不适用。',
         example_ids=['HSD51045']),
    dict(mode='split', name='左右分区', summary='分成左右两区，各自排列不同图案。',
         note='至少选两张，前半用于左区、后半用于右区。当前是图案分区；如需两种底纹，请使用自备组合底图，不自动复制案例底纹。',
         example_ids=['HSD68027']),
    dict(mode='stacked', name='上下分区', summary='分成上下两块大区域，各自排列图案。',
         note='至少选两张，前半用于上区、后半用于下区。这不是窄边饰；案例中的两种底纹需使用自备组合底图。',
         example_ids=['HSD31412']),
    dict(mode='opposed', name='正倒交替', summary='相邻图案按正立、倒置180度交替重复。',
         note='按选择顺序轮换，只旋转、不镜像，不会把文字左右翻反。案例中的人物和底纹不会自动复制。',
         example_ids=['HSD31296']),
)


class RibbonExamples:
    def __init__(self, directory):
        self.directory = Path(directory)

    def image(self, code):
        """Read and verify once; send these same bytes, never reopen by path."""
        expected = IMAGE_SPECS.get(code)
        if expected is None:
            return None
        try:
            if self.directory.is_symlink() or not self.directory.is_dir():
                return None
            path = self.directory / (code + '.jpg')
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or before.st_size != expected[2]:
                return None
            with path.open('rb') as stream:
                data = stream.read(expected[2] + 1)
            if len(data) != expected[2] or hashlib.sha256(data).hexdigest() != expected[3]:
                return None
            return data
        except (OSError, ValueError):
            return None

    def catalog(self):
        examples = []
        for spec in EXAMPLES:
            code = spec['code']
            image_spec = IMAGE_SPECS[code]
            available = self.image(code) is not None
            examples.append(dict(spec, id=code, width=image_spec[0], height=image_spec[1],
                                 available=available,
                                 image_url=(f'/api/ribbon/layout-examples/{code}/image?v={image_spec[3][:16]}'
                                            if available else None)))
        return dict(modes=[dict(mode) for mode in MODE_GUIDES], examples=examples,
                    source_name='公司图库',
                    note='案例只用于理解排法，查看不会更改当前选择或调用模型。图库覆盖水印不是设计文字。')
