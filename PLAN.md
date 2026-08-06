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
| 人脸检测 | MediaPipe 1.0 Tasks API 的 `FaceLandmarker` | 478 点模型提供下巴、额头、虹膜和眼角坐标 |
| 打印 | PySide6 `QPrinter` + `QPageSize`，全尺寸模式 | 唯一能锁定物理尺寸不被驱动缩放的方案 |
| 打包 | PyInstaller **onedir**（不是 onefile） | onefile 每次启动都要把 ~180MB 模型解压到临时目录，慢 |
| 代码传输 | 手动打包 zip 传到 Windows 机器 | 用户环境无法访问 GitHub |

**Python 用 3.13，Mac 和 Windows 两边必须一致。** 已在 Mac（3.13.7 / arm64）实测：mediapipe 1.0.0、rembg 2.0.77、onnxruntime 1.23.2、opencv 5.0.0、PySide6 6.9.3 全部装得上、跑得通。不要用 3.14，太新，部分包还没跟上。

MediaPipe 1.0 **删除了旧的 `mp.solutions` API**，`mp.solutions.face_detection` 会直接报 `AttributeError`。新写法：

```python
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions

opts = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='assets/models/face_landmarker.task'),
    num_faces=5,
    output_face_blendshapes=False,
    output_facial_transformation_matrixes=False,
)
landmarker = FaceLandmarker.create_from_options(opts)
result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_array))
```

FaceLandmarker 的 landmark 坐标是**归一化坐标**（0-1），必须分别乘图像宽高转成绝对像素。当前使用 152（下巴）、10（额头）、468-477（两侧虹膜）和 33/263（两眼外角）。最多检测 5 张脸，按全部 landmark 外接矩形面积选择最大脸。

FaceLandmarker 模型要提前下好（约 3.6MB，来自 Google CDN）：
```bash
curl -L -o assets/models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
```

`blaze_face_short_range.tflite` 暂时继续随包保留，但运行时代码不引用。原因是 Windows 真机尚未验证，目标 Xeon E5-2680 v2 没有 AVX2；FaceLandmarker 真机通过后再单独清理回退资产。

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

### 裁剪规格（FaceLandmarker 纵向基准）

**不追求国标级精度。** 目标是自动算出一个八成对的框，人眼扫一下、需要时手动拖一下，比追求全自动完美可靠。

缩放和纵向位置仍由两个独立参数控制：

```
H = 1.8584        # 暂定值：裁剪高 = 额头到下巴的欧氏距离 × H，控制头的大小
EYE_LINE = 0.42   # 眼线基础位置，控制上下构图
LOWER_EDGE_LIFT_RATIO = 0.05
```

算法三步，没有第四步：

1. `face_height = hypot(chin.x - forehead.x, chin.y - forehead.y)`；裁剪高 = `face_height × H`，裁剪宽 = 裁剪高 × (规格宽 mm / 规格高 mm)
2. 水平：两侧虹膜质心的中点 x 居中
3. 竖直：`top = 眼睛中点 y − 裁剪高 × (EYE_LINE + LOWER_EDGE_LIFT_RATIO)`

缩放基准改成纵向解剖距离，是因为目标量本身就是头部在画面里的纵向占比。landmark 10 和 152 是模型直接检测出的额头与下巴点，欧氏距离对小角度旋转不变；它不再把会被蓬松头发污染的横向 bbox 宽度转换成裁剪高度。`bbox_width` 只保留作诊断，不参与缩放。

这不是恢复已作废的“国标四约束”方案：运行时仍不检测或推算头顶，也不用发量联动裁剪框。头发最高点只在离线样片校准中通过 rembg alpha 测量，用来反解候选 H。

校准时，每张样片只抠图一次并缓存 alpha：朴素 hair-top 是首个 `alpha > 0` 的行，只作杂点诊断；稳健 hair-top 是首个满足“该行 `alpha >= 128` 的像素数至少为 8”的行。实际反解只使用稳健值：

```
d = (eyes_y - robust_hair_top_y) / face_height
H = median(d) / (EYE_LINE + LOWER_EDGE_LIFT_RATIO - target)
```

分别生成 target 为 6%、9%、12% 的三组候选图。本轮暂用 9% 组得到的 `H=1.8584`，最终值等目视九张候选图后再决定。跨样片余白标准差等于 `pstdev(d) / H`，会随 H 增大机械下降，只能作发量差异诊断，不能作为 H 的选择标准。

两个独立的失败标志，不要合并：

- `insufficient_space`：框超出原图边界 → 往回收并提示「原图裁剪空间不足，建议重拍留多点余量」，不许静默拉伸或补黑边
- `insufficient_resolution`：框在原图内但像素小于规格 300 DPI 所需 → 放大会糊，需提示

Pillow 最终裁剪前统一把浮点框量化成整数边界：先 `width = round(box.width)`，再 `height = round(width / aspect_ratio)`，最后按浮点框中心定位左上角并夹入原图。不要按规格最简整数比吸附，三寸 55:84 会产生 55×84px 的粗粒度并误触分辨率警告。

手动框始终锁定规格比例：拖动四角缩放、拖框移动；滚轮每格按 `1.02` 缩放，Shift+滚轮按 `1.005`；方向键移动 1 个图像像素，Shift+方向键移动 10 个图像像素。所有路径都必须夹在图像边界内。裁剪画布右下角显示实际整数裁剪尺寸，低于 300 DPI 需求时使用警告色。

检测不到人脸时不要崩，退化成手动裁剪模式，给用户一个可拖拽的固定比例框。

### 换底（实验性功能，不是主路径）

**主路径是「拍什么底就出什么底」。** 默认行为是保持原背景，不抠图。换色作为实验性功能保留，效果受原图背景色决定，不追求专业水平。

原因是 color spill，这是信息丢失，不是模型精度问题——**换更强的抠图模型也解决不了。**

半透明的发丝像素，其颜色是 `前景色 × α + 背景色 × (1−α)`，原背景色已经烧进像素里了。抠图只能算出 α，没法把混进去的白色还原成头发本来的颜色。所以：

- **白底原图 → 蓝/红底**：灰白色的碎发贴到蓝底上，成为一圈明显白毛边。实测确认
- **蓝底原图 → 蓝底**：碎发本身是深灰蓝，贴回蓝底几乎看不出接缝，效果很好。实测确认

专业工具靠额外的去色溢出（despill）算法处理，不是靠更好的分割模型。本项目不做 despill。

由此定下的三条：

1. **默认底色 = 保持原背景**，只在背景脏或有杂物时才抠图，抠完仍贴回同色底
2. **跨色换底给明确提示**：「白底照片换蓝/红底会在发丝处留白边，建议直接用对应背景色重拍」
3. **手动修补画笔降级为可选**（原定必做）。换底既是次要功能，画笔的优先级也跟着降，工夫放在裁剪和打印上更值

实现（功能本身仍要做对）：

1. rembg 出 RGBA，拿到 alpha 通道
2. alpha 轻微羽化（1-2px 高斯）避免硬边锯齿
3. 纯色底图上做 alpha 合成
4. 三种底色：白 `#FFFFFF`、蓝 `#438EDB`（国标证件照蓝，不是纯蓝）、红 `#FF0000`

顺带一个同源问题：**浅色衣服在白底原图上会被当成前景留下**，换深色底后很明显。`crop.py` 的 `LOWER_EDGE_LIFT_RATIO` 把裁剪下缘上移、让衣服少进画面，能缓解大部分情况。蓝底原图因为衣服和背景对比明显，抠得干净很多。

## 界面

单窗口三栏，不要向导式多步骤：

```
┌─────────────────────────────────────────────┐
│  [导入照片]                          [打印]  │
├──────────┬──────────────────┬───────────────┤
│  原图     │   裁剪+换底预览    │  相纸排版预览  │
│  缩略图   │   （可拖拽调整框）  │  （显示"共12张"）│
├──────────┴──────────────────┴───────────────┤
│ 规格: [一寸▾]  底色: ●原底 ○白 ○蓝 ○红        │
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
│   ├── detect.py            # MediaPipe FaceLandmarker，输出解剖点、虹膜中点和倾斜角
│   ├── crop.py              # 裁剪框计算（face_height × H + EYE_LINE）
│   ├── matting.py           # rembg 抠图 + 换底 + alpha 修补
│   ├── layout.py            # solve_layout + 网格合成
│   └── export.py            # 纯 Pillow 的 PNG / PDF 导出
├── ui/
│   ├── main_window.py
│   ├── printing.py          # QPrinter 直接打印
│   ├── crop_view.py         # 可拖拽裁剪框
│   └── brush_view.py        # alpha 修补画笔
├── assets/models/
│   ├── isnet-general-use.onnx          # rembg 抠图，170MB
│   ├── face_landmarker.task            # 当前人脸 landmark 检测，约 3.6MB
│   └── blaze_face_short_range.tflite   # Windows 未验证前保留的回退资产
├── specs.json               # 10 个可选规格：毫米尺寸 + 电子照目标像素
├── tests/
├── requirements.txt
└── build.spec
```

导出与打印按依赖边界拆分：`core/export.py` 只使用 Pillow，`ui/printing.py` 承载 QPrinter，确保 `core/` 不引入 PySide6。

`core/` 里不许出现任何 PySide6 import，保证核心逻辑能脱离界面在 Mac 上跑单元测试。

## 分阶段执行

每阶段做完就在 Mac 上验证，别憋到最后一起调。

**阶段 1：核心管线（Mac 上完成，不碰界面）**
写 `units.py` + `layout.py` + `specs.json`，配单元测试断言上面 10 个可选规格的 300 DPI 排版像素、张数、布局和门店电子照目标像素。再接 `detect.py` + `crop.py`，用几张真实手机照片跑通，输出裁剪结果存到本地看效果。最后 `matting.py` 换三种底色。
产出：一个命令行脚本，输入图片路径和规格，输出排好版的 PNG。**这一步跑通就等于项目成了 70%。**

**阶段 2：界面**
PySide6 套上去，三栏布局，抠图丢后台线程。**可拖拽裁剪框是必做**（单一 K 值对不同发型必然有偏差，手动微调是刚需）。修补画笔可选，等主路径跑顺了再看要不要做。Mac 上就能看全部效果。

**阶段 3：打印与导出**
`printing.py` 三条路径都实现。Mac 上先验证导出的 PNG/PDF 物理尺寸对不对（用预览打开看文档属性里的尺寸是不是 102×152mm）。

**阶段 4：Windows 打包与真机验证**
写 `build.spec`，把代码 + 三个模型资产打包成 zip 传到 Windows 机器。Windows 上装 **Python 3.13**（和 Mac 一致）→ `pip install -r requirements.txt` → `pyinstaller build.spec` → 跑 exe。真机必须验证：FaceLandmarker 和抠图模型加载都不联网、抠图能出结果、**实际打印一张量一下尺寸对不对**。BlazeFace 只作为回退资产保留。

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

- **环境**：Python 3.13.7 虚拟环境 `.venv/`，全部依赖装好并验证 import 通过；FaceLandmarker、BlazeFace 回退资产和 rembg 模型均已准备
- **`units.py`**：mm↔px 唯一转换处，300 DPI
- **`layout.py`**：`solve_layout` 四组合求解，10 个规格的张数、布局全部与验收表一致。并列时优先级为：张数 → **照片不旋转** → 横向相纸 → 列数。照片不旋转必须排在相纸方向之前，否则一寸/简历照/四六级会被躺倒排版（张数相同但打印出来方向不对、裁剪时容易搞混）
- **`specs.json`**：10 个规格，毫米尺寸 + 门店电子照目标像素
- **`detect.py`**：MediaPipe 1.0 FaceLandmarker，输出下巴、额头、虹膜中点、欧氏脸高和倾斜角，最多检测 5 张脸并选最大脸
- **`crop.py`**：欧氏 face_height × H + EYE_LINE 两参数，另有 `LOWER_EDGE_LIFT_RATIO=0.05` 上移下缘减少衣服入画
- **`matting.py`**：rembg 离线抠图、session 单例复用、1.5px 羽化、三种底色
- **`idphoto_cli.py`**：`图片 规格 底色` → `out/` PNG，阶段 1 验收产物已跑通
- 测试 20 个全绿（含真跑 MediaPipe 的集成测试）

**阶段 1 已完成。** 三张样片实测输出 1205×1795、300 DPI、竖向排版正确。

已作废并修正的五个错误假设（都是实测推翻的，别改回去）：

1. Python 锁 3.11 —— 实测 3.13 全部依赖可用，MediaPipe 已出 1.0
2. `mp.solutions` API —— MediaPipe 1.0 已删除，改用 Tasks API
3. 国标四约束裁剪 —— BlazeFace bbox 上下沿不对应解剖位置，先改为两参数；当前进一步用 FaceLandmarker 额头到下巴的欧氏距离作为纵向缩放基准，但仍不推算头顶
4. 并列优先级「横向相纸优先」—— 导致一寸等三个规格躺倒排版，改为照片不旋转优先
5. 换底是核心功能、修补画笔必做 —— color spill 使跨色换底无法做好，换底降为实验功能，画笔降为可选

## 下一步

阶段 2 界面。三栏布局 + 可拖拽裁剪框（必做），抠图放后台线程。底色默认「保持原底」。

先做骨架和裁剪框，画笔放最后再决定要不要做。

## 验收标准

- 排版求解函数输出与上表完全一致
- 手机拍的照片能自动裁出比例正确的证件照，人脸居中、头顶余白肉眼看着合理（不追求国标级精度，允许发型差异带来的偏差，靠手动微调兜底）
- 保持原底（主路径）时输出干净无瑕疵；跨色换底作为实验功能，允许发丝白边，但要有提示
- 导出 PDF 物理尺寸精确为 102×152mm
- 实际打印后用尺子量，单张照片尺寸误差 < 0.5mm
- Windows 上双击 exe 能启动，全程不联网

## 相关

- [[Project/证件照处理/产品定位]]
