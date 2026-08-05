---
created: 2026-08-05
---

# 证件照排版软件 — 开发规划

给 Codex 执行用的施工图。目标是把「手机拍照 → PS 手动裁剪换底排版」这条链路压缩成「拖入照片 → 点打印」。

## 目标是什么

一个 Windows 10 桌面软件，输入一张手机拍的人像，输出一张排满证件照的 6 寸（4R）相纸图，直接送打印机。打印完只剩人工裁剪。

不做：美白、祛痘、瘦脸、滤镜、批量流水线、云端。

## 技术决策（已定，不要改）

| 项 | 选择 | 原因 |
|---|---|---|
| 语言 / GUI | Python 3.13 + PySide6 | Mac 上能直接跑起来看界面，图像生态最全 |
| 图像处理 | Pillow + OpenCV | 裁剪、合成、排版 |
| 抠图 | rembg + `isnet-general-use` 模型，CPU 推理 | 发丝边缘接近专业水平；Xeon E5-2680 v2 单张 1-3 秒够用 |
| 人脸检测 | MediaPipe 1.0 Tasks API 的 `FaceDetector` | 拿 bbox 宽度和双眼坐标算裁剪框 |
| 打印 | PySide6 `QPrinter` + `QPageSize`，全尺寸模式 | 唯一能锁定物理尺寸不被驱动缩放的方案 |
| 打包 | PyInstaller **onedir**（不是 onefile） | onefile 每次启动都要把 ~180MB 模型解压到临时目录，慢 |
| 代码传输 | 手动打包 zip 传到 Windows 机器 | 用户环境无法访问 GitHub |

**Python 用 3.13，Mac 和 Windows 两边必须一致。** 已在 Mac（3.13.7 / arm64）实测：mediapipe 1.0.0、rembg 2.0.77、onnxruntime 1.23.2、opencv 5.0.0、PySide6 6.9.3 全部装得上、跑得通。不要用 3.14，太新，部分包还没跟上。

MediaPipe 1.0 **删除了旧的 `mp.solutions` API**，`mp.solutions.face_detection` 会直接报 `AttributeError`。新写法：

```python
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions

opts = FaceDetectorOptions(
    base_options=BaseOptions(model_asset_path='assets/models/blaze_face_short_range.tflite'),
    min_detection_confidence=0.5,
)
detector = FaceDetector.create_from_options(opts)
result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_array))
```

`detections[0].bounding_box` 是绝对像素（`origin_x/origin_y/width/height`），而 `keypoints` 是**归一化坐标**（0-1，需乘图像宽高）。两者单位不同，容易混。keypoints 顺序：0 右眼、1 左眼、2 鼻尖、3 嘴中心、4 右耳、5 左耳。

人脸检测模型也要提前下好（224KB，来自 Google CDN 而非 GitHub，Windows 那台大概能直连）：
```bash
curl -L -o assets/models/blaze_face_short_range.tflite \
  https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite
```

## 两个必踩的坑（先解决，否则后面全白干）

### 坑 1：rembg 模型默认从 GitHub 下载，目标机器下不了

模型必须**在 Mac 上提前下好**，随代码一起传过去，并在程序启动时把 `U2NET_HOME` 指到打包目录。

Mac 上准备（放进 `assets/models/`）：
```bash
mkdir -p assets/models
curl -L -o assets/models/isnet-general-use.onnx \
  https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx
```

程序入口**在 import rembg 之前**必须先设环境变量，顺序错了就会去联网：
```python
import os, sys
base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
os.environ['U2NET_HOME'] = os.path.join(base, 'assets', 'models')
from rembg import new_session, remove   # 必须在设置之后
```

注意是 `U2NET_HOME`，指向**目录**不是文件；网上大量答案写 `U2NET_PATH`，是错的。文件名必须精确等于 `isnet-general-use.onnx`，改名会触发重新下载。如果校验和不匹配 rembg 也会重新联网下载，实在卡住就设 `MODEL_CHECKSUM_DISABLED=1`。

### 坑 2：Windows 上 onnxruntime 打包后 DLL 加载失败

`.spec` 里必须显式收集动态库，否则报 `DLL load failed while importing onnxruntime_pybind11_state`：
```python
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
datas = collect_data_files('onnxruntime') + [('assets/models/isnet-general-use.onnx', 'assets/models')]
binaries = collect_dynamic_libs('onnxruntime')
hiddenimports = ['numpy','PIL','scipy','scipy.ndimage','skimage','skimage.morphology',
                 'pymatting','pymatting.alpha','pymatting.foreground','pymatting.util',
                 'tqdm','pooch','jsonschema','onnxruntime']
```
另外：环境里**只能装 `onnxruntime`，不能同时装 `onnxruntime-gpu`**，共存会导致同样的报错。RX 580 是 AMD 卡，onnxruntime 的 CUDA 加速用不上，老老实实走 CPU。

## 核心算法规格

### 相纸与坐标系

4R 相纸 = 102 × 152 mm。全程按 **300 DPI** 计算，画布 1205 × 1795 px。

mm 转 px：`px = round(mm / 25.4 * 300)`。整个项目只允许有这一个转换函数，不许各处手写。

### 可选规格与排版数量表（默认 gap=1mm，margin=1mm，已验算）

本阶段收录用户提供的门店尺寸表上半部分 10 个常用规格；下半部分“回执照片相关标准”暂不加入。

| 规格 | 尺寸 mm | 门店电子照像素 | 300 DPI 排版像素 | 张数 | 布局 | 相纸旋转 |
|---|---|---|---|---|---|---|
| 一寸 | 25×35 | 295×413 | 295×413 | 12 | 3列×4行 | 竖向 |
| 二寸 | 35×49 | 413×579 | 413×579 | 8 | 4列×2行 | 横向 |
| 三寸 | 55×84 | 649×991 | 650×992 | 2 | 2列×1行 | 横向 |
| 大一寸 | 33×48 | 390×567 | 390×567 | 8 | 4列×2行 | 横向 |
| 小一寸 | 22×32 | 260×378 | 260×378 | 18 | 6列×3行 | 横向 |
| 大二寸 | 35×53 | 413×626 | 413×626 | 4 | 4列×1行 | 横向 |
| 小二寸 | 35×45 | 413×531 | 413×531 | 8 | 4列×2行 | 横向 |
| 简历照 | 25×35 | 295×413 | 295×413 | 12 | 3列×4行 | 竖向 |
| 普通话水平测试 | 33×48 | 390×567 | 390×567 | 8 | 4列×2行 | 横向 |
| 英语四六级 | 12×16 | 144×192 | 142×189 | 56 | 7列×8行 | 竖向 |

打印排版以“尺寸 mm”为物理尺寸事实源，统一通过 `units.py` 换算 300 DPI 像素。门店电子照像素只用于导出指定像素的电子照片，不参与 4R 排版计算。三寸和英语四六级的两种像素值不同是两套标准本身的差异，不要为了让它们相等而绕过统一换算函数。

`specs.json` 中 10 个名称都保留为独立可选项，即使简历照与一寸、普通话水平测试与大一寸尺寸相同。每项同时保存毫米尺寸和门店电子照目标像素；排版求解只读取毫米尺寸。

**这张表是验收基准，但不要把数字硬编码进代码。** 写一个求解函数，四种组合（照片竖放/横放 × 相纸竖向/横向）全试一遍取最大张数，跑出来的结果应该和上表一致。这样以后加规格自动就对。

```
def solve_layout(photo_w_mm, photo_h_mm, gap=1.0, margin=1.0, paper=(102,152)):
    候选 = []
    for (w, h) in [(photo_w_mm, photo_h_mm), (photo_h_mm, photo_w_mm)]:   # 照片是否旋转90°
        for (pw, ph) in [paper, paper[::-1]]:                              # 相纸竖向/横向
            cols = int((pw - 2*margin + gap) // (w + gap))
            rows = int((ph - 2*margin + gap) // (h + gap))
            if cols > 0 and rows > 0:
                候选.append((cols*rows, cols, rows, 是否旋转, pw, ph))
    return max(候选)   # 按张数取最大
```

排完后把整个网格在相纸上**居中**，别左上角堆着。每张照片四周画 0.3mm 浅灰细线当裁剪参考线（可开关）。

### 裁剪规格（已用真实样片实测定稿）

**不追求国标级精度。** 目标是自动算出一个八成对的框，人眼扫一下、需要时手动拖一下，比追求全自动完美可靠。

只用两个参数，各自独立可调：

```
K = 1.55          # 裁剪宽 = bbox 宽 × K，控制头的大小
EYE_LINE = 0.42   # 眼睛中点位于裁剪框高度的 42% 处，控制上下位置
```

算法三步，没有第四步：

1. 裁剪宽 = `bbox.width × K`，裁剪高 = 裁剪宽 × (规格高 mm / 规格宽 mm)
2. 水平：双眼中点 x 居中
3. 竖直：`top = 眼睛中点 y − 裁剪高 × EYE_LINE`

**不要推算头顶和下巴位置。** BlazeFace 的 bbox 是正方形（`w == h`，三张样片实测确认），上沿不在眉毛、下沿远超下巴延伸到脖子肩膀，拿上下沿当解剖学基准会引入不稳定误差。只有 bbox 宽度和眼睛坐标是可靠的：宽度只跟人脸宽度相关，眼睛是直接检测出来的、不是推断的。

原「头顶留白 7-12% + 头高 60-72% + 眼线 45% + 中轴居中」四约束联动方案已作废：那是照相馆验收标准，不适合用来算框——四个约束互相牵制、都依赖推断的头顶下巴、误差叠加。

三张真实手机样片实测（3072×4096，一寸规格）：

| 样片 | 裁剪框 | 越界 | 裁后像素 vs 需求 295×413 |
|---|---|---|---|
| 平头男性 | 1559×2183 | 无 | 5 倍余量 |
| 蓬松短发男性 | 1617×2263 | 无 | 5 倍余量 |
| 长发女性 | 1626×2276 | 无 | 5 倍余量 |

发型差异会导致头顶余白不一致（蓬松发型偏紧、平头偏松），这是单一系数的固有局限，靠界面手动微调兜底，不要试图用更复杂的算法消除。

两个独立的失败标志，不要合并：

- `insufficient_space`：框超出原图边界 → 往回收并提示「原图裁剪空间不足，建议重拍留多点余量」，不许静默拉伸或补黑边
- `insufficient_resolution`：框在原图内但像素小于规格 300 DPI 所需 → 放大会糊，需提示

检测不到人脸时不要崩，退化成手动裁剪模式，给用户一个可拖拽的固定比例框。

### 换底

1. rembg 出 RGBA，拿到 alpha 通道
2. alpha 做轻微羽化（1-2px 高斯）避免硬边锯齿
3. 纯色底图上做 alpha 合成
4. 三种底色定义：
   - 白底 `#FFFFFF`
   - 蓝底 `#438EDB`（国标常用证件照蓝，不是纯蓝）
   - 红底 `#FF0000`

**深色底（红、蓝）会把抠图瑕疵放大得非常明显**，白底看不出的毛边换蓝底就现形了。所以必须配一个手动修补画笔：放大预览，画笔涂抹增删 alpha，笔刷大小可调。这个不是可选功能，是成品能不能用的关键。

## 界面

单窗口三栏，不要向导式多步骤：

```
┌─────────────────────────────────────────────┐
│  [导入照片]                          [打印]  │
├──────────┬──────────────────┬───────────────┤
│  原图     │   裁剪+换底预览    │  相纸排版预览  │
│  缩略图   │   （可拖拽调整框）  │  （显示"共12张"）│
├──────────┴──────────────────┴───────────────┤
│ 规格: [一寸▾]  底色: ○白 ○蓝 ○红             │
│ 间距: [1.0]mm  边距: [1.0]mm  ☑裁剪线        │
│ [修补画笔] [导出PNG] [导出PDF]                │
└─────────────────────────────────────────────┘
```

改任何参数，右侧排版预览和张数立即刷新。抠图慢，放后台线程跑，跑的时候显示进度不要冻住界面。

## 打印（最容易翻车的一步）

必须用 `QPrinter` 的全尺寸模式，禁止任何自动缩放：

```python
printer = QPrinter(QPrinter.HighResolution)
printer.setPageSize(QPageSize(QSizeF(102, 152), QPageSize.Millimeter, "4R"))
printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
printer.setFullPage(True)   # 关键，否则 Qt 会按可打印区域再缩一次
```

同时提供**导出 PNG（300dpi）和导出 PDF（物理尺寸精确）**两条兜底路径。直接打印在不同驱动上行为不一致，导出 PDF 再用系统看图工具打印往往更稳。

打印机驱动里也要手动关掉「适应纸张」「无边距缩放」这类选项，这条写进 README 提醒用户。

## 项目结构

```
idphoto/
├── main.py                  # 入口，第一件事就是设 U2NET_HOME
├── core/
│   ├── units.py             # mm↔px 唯一转换处
│   ├── detect.py            # MediaPipe FaceDetector，输出 bbox 宽 + 双眼坐标
│   ├── crop.py              # 裁剪框计算（K + EYE_LINE 两参数）
│   ├── matting.py           # rembg 抠图 + 换底 + alpha 修补
│   ├── layout.py            # solve_layout + 网格合成
│   └── printing.py          # QPrinter / PDF / PNG 导出
├── ui/
│   ├── main_window.py
│   ├── crop_view.py         # 可拖拽裁剪框
│   └── brush_view.py        # alpha 修补画笔
├── assets/models/
│   ├── isnet-general-use.onnx          # rembg 抠图，170MB
│   └── blaze_face_short_range.tflite   # 人脸检测，224KB
├── specs.json               # 10 个可选规格：毫米尺寸 + 电子照目标像素
├── tests/
├── requirements.txt
└── build.spec
```

`core/` 里不许出现任何 PySide6 import，保证核心逻辑能脱离界面在 Mac 上跑单元测试。

## 分阶段执行

每阶段做完就在 Mac 上验证，别憋到最后一起调。

**阶段 1：核心管线（Mac 上完成，不碰界面）**
写 `units.py` + `layout.py` + `specs.json`，配单元测试断言上面 10 个可选规格的 300 DPI 排版像素、张数、布局和门店电子照目标像素。再接 `detect.py` + `crop.py`，用几张真实手机照片跑通，输出裁剪结果存到本地看效果。最后 `matting.py` 换三种底色。
产出：一个命令行脚本，输入图片路径和规格，输出排好版的 PNG。**这一步跑通就等于项目成了 70%。**

**阶段 2：界面**
PySide6 套上去，三栏布局，抠图丢后台线程。加可拖拽裁剪框和修补画笔。Mac 上就能看全部效果。

**阶段 3：打印与导出**
`printing.py` 三条路径都实现。Mac 上先验证导出的 PNG/PDF 物理尺寸对不对（用预览打开看文档属性里的尺寸是不是 102×152mm）。

**阶段 4：Windows 打包与真机验证**
写 `build.spec`，把代码 + 两个模型打包成 zip 传到 Windows 机器。Windows 上装 **Python 3.13**（和 Mac 一致）→ `pip install -r requirements.txt` → `pyinstaller build.spec` → 跑 exe。真机必须验证：两个模型加载都不联网、抠图能出结果、**实际打印一张量一下尺寸对不对**。

注意 Mac 是 arm64、Windows 是 x86_64，架构不同，Mac 上装好的包不能直接拷过去，Windows 必须自己 `pip install` 一遍。

## 传输与打包流程（无 GitHub 环境）

Mac 上打包源码（排除虚拟环境和缓存，但要带上模型）：
```bash
cd idphoto && zip -r ../idphoto-src.zip . \
  -x "*.venv/*" "*__pycache__/*" "*.DS_Store" "build/*" "dist/*"
```

模型 ~180MB，微信传文件、U 盘、局域网共享都行。Windows 机器上还需要联网装一次 pip 依赖（PyPI 通常能访问，和 GitHub 不同）。如果 PyPI 也不通，在 Mac 上用 `pip download -d wheels -r requirements.txt --platform win_amd64 --only-binary=:all: --python-version 3.13` 把 wheel 全下好一起传，Windows 上 `pip install --no-index --find-links wheels -r requirements.txt`。

## 当前进展

代码在 `~/Projects/idphoto/`（库外，避免 iCloud 同步虚拟环境和模型），git 已初始化，`PLAN.md` 是本文件的副本，`./sync-plan.sh` 从库同步。

已完成：

- **环境**：Python 3.13.7 虚拟环境 `.venv/`，全部依赖装好并验证 import 通过；两个模型已下载，rembg 离线加载确认不联网
- **`units.py`**：mm↔px 唯一转换处，300 DPI
- **`layout.py`**：`solve_layout` 四组合求解，10 个规格的张数、布局全部与验收表一致。并列时优先级为：张数 → 照片不旋转 → 横向相纸 → 列数
- **`specs.json`**：10 个规格，毫米尺寸 + 门店电子照目标像素
- **`detect.py` / `crop.py`**：已写但**基于已作废的国标四约束方案，需按新的两参数规则重写**
- 测试 10 个，纯逻辑部分全绿

已作废并修正的三个错误假设：

1. Python 锁 3.11 —— 实测 3.13 全部依赖可用，MediaPipe 已出 1.0
2. `mp.solutions` API —— MediaPipe 1.0 已删除，改用 Tasks API
3. 国标四约束裁剪 —— BlazeFace bbox 是正方形，上下沿不对应眉毛下巴，改用 K + EYE_LINE 两参数

## 下一步

按新的两参数裁剪规则重写 `core/detect.py` 和 `core/crop.py`：`detect.py` 改用 MediaPipe 1.0 Tasks API，只输出 bbox 宽度和双眼坐标；`crop.py` 删掉 CROWN_RATIO 和四约束联动，只留 K 和 EYE_LINE。测试用三张真实样片验证无越界。

之后是 `matting.py`（rembg 抠图 + 三种底色），然后阶段 1 收尾的命令行脚本。

## 验收标准

- 排版求解函数输出与上表完全一致
- 手机拍的照片能自动裁出比例正确的证件照，人脸居中、头顶余白肉眼看着合理（不追求国标级精度，允许发型差异带来的偏差，靠手动微调兜底）
- 换蓝底后发丝边缘无明显白边（修补画笔可补救）
- 导出 PDF 物理尺寸精确为 102×152mm
- 实际打印后用尺子量，单张照片尺寸误差 < 0.5mm
- Windows 上双击 exe 能启动，全程不联网

## 相关

- [[Project/证件照处理/产品定位]]
