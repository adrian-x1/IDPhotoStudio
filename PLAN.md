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
| 语言 / GUI | Python 3.11 + PySide6 | Mac 上能直接跑起来看界面，图像生态最全 |
| 图像处理 | Pillow + OpenCV | 裁剪、合成、排版 |
| 抠图 | rembg + `isnet-general-use` 模型，CPU 推理 | 发丝边缘接近专业水平；Xeon E5-2680 v2 单张 1-3 秒够用 |
| 人脸检测 | MediaPipe Face Detection | 定位五官算裁剪框 |
| 打印 | PySide6 `QPrinter` + `QPageSize`，全尺寸模式 | 唯一能锁定物理尺寸不被驱动缩放的方案 |
| 打包 | PyInstaller **onedir**（不是 onefile） | onefile 每次启动都要把 ~180MB 模型解压到临时目录，慢 |
| 代码传输 | 手动打包 zip 传到 Windows 机器 | 用户环境无法访问 GitHub |

Python 3.11 不要换 3.12/3.13，MediaPipe 和 onnxruntime 的 wheel 在新版本上经常缺。

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

### 排版数量表（默认 gap=1mm，margin=1mm，已验算）

| 规格 | 尺寸 mm | 像素 | 张数 | 布局 | 相纸旋转 |
|---|---|---|---|---|---|
| 一寸 | 25×35 | 295×413 | 12 | 4列×3行 | 横向 |
| 小一寸 | 22×32 | 260×378 | 18 | 6列×3行 | 横向 |
| 大一寸 | 33×48 | 390×567 | 8 | 4列×2行 | 横向 |
| 二寸 | 35×49 | 413×579 | 8 | 4列×2行 | 横向 |
| 小二寸 | 35×45 | 413×531 | 8 | 4列×2行 | 横向 |
| 大二寸 | 35×53 | 413×626 | 4 | 4列×1行 | 横向 |

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

### 裁剪规格

MediaPipe 检测人脸后按国标算裁剪框，不要简单地按人脸框等比放大：

- 头顶留白 = 照片高度的 **7%–12%**
- 头部（下巴到头顶）占照片高度 **60%–72%**
- 双眼水平线位于照片顶部往下 **约 45%** 处
- 人脸中轴线水平居中

先按头高定 scale，再按眼睛高度定竖直偏移，最后按中轴线定水平偏移。如果算出的框超出原图边界，就往回收并提示用户「原图裁剪空间不足，建议重拍留多点余量」，不要静默拉伸或补黑边。

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
│   ├── detect.py            # MediaPipe 人脸检测
│   ├── crop.py              # 国标裁剪框计算
│   ├── matting.py           # rembg 抠图 + 换底 + alpha 修补
│   ├── layout.py            # solve_layout + 网格合成
│   └── printing.py          # QPrinter / PDF / PNG 导出
├── ui/
│   ├── main_window.py
│   ├── crop_view.py         # 可拖拽裁剪框
│   └── brush_view.py        # alpha 修补画笔
├── assets/models/isnet-general-use.onnx
├── specs.json               # 证件照规格表，可扩展
├── tests/
├── requirements.txt
└── build.spec
```

`core/` 里不许出现任何 PySide6 import，保证核心逻辑能脱离界面在 Mac 上跑单元测试。

## 分阶段执行

每阶段做完就在 Mac 上验证，别憋到最后一起调。

**阶段 1：核心管线（Mac 上完成，不碰界面）**
写 `units.py` + `layout.py` + `specs.json`，配单元测试断言上面那张数量表。再接 `detect.py` + `crop.py`，用几张真实手机照片跑通，输出裁剪结果存到本地看效果。最后 `matting.py` 换三种底色。
产出：一个命令行脚本，输入图片路径和规格，输出排好版的 PNG。**这一步跑通就等于项目成了 70%。**

**阶段 2：界面**
PySide6 套上去，三栏布局，抠图丢后台线程。加可拖拽裁剪框和修补画笔。Mac 上就能看全部效果。

**阶段 3：打印与导出**
`printing.py` 三条路径都实现。Mac 上先验证导出的 PNG/PDF 物理尺寸对不对（用预览打开看文档属性里的尺寸是不是 102×152mm）。

**阶段 4：Windows 打包与真机验证**
写 `build.spec`，把代码 + 模型打包成 zip 传到 Windows 机器。Windows 上装 Python 3.11 → `pip install -r requirements.txt` → `pyinstaller build.spec` → 跑 exe。真机必须验证：模型加载不联网、抠图能出结果、**实际打印一张量一下尺寸对不对**。

## 传输与打包流程（无 GitHub 环境）

Mac 上打包源码（排除虚拟环境和缓存，但要带上模型）：
```bash
cd idphoto && zip -r ../idphoto-src.zip . \
  -x "*.venv/*" "*__pycache__/*" "*.DS_Store" "build/*" "dist/*"
```

模型 ~180MB，微信传文件、U 盘、局域网共享都行。Windows 机器上还需要联网装一次 pip 依赖（PyPI 通常能访问，和 GitHub 不同）。如果 PyPI 也不通，在 Mac 上用 `pip download -d wheels -r requirements.txt --platform win_amd64 --only-binary=:all: --python-version 3.11` 把 wheel 全下好一起传，Windows 上 `pip install --no-index --find-links wheels -r requirements.txt`。

## 当前进展

规划完成，代码尚未开始。已定技术栈与算法规格，已验算排版数量表，已核实 rembg 离线模型与 onnxruntime 打包两个坑的解法。

## 下一步

在 Mac 上建项目骨架，装依赖，下载 `isnet-general-use.onnx` 到 `assets/models/`，然后让 Codex 做阶段 1 的 `units.py` + `layout.py` + 数量表单元测试。**先只做这一个文件加测试，跑绿了再往下。**

## 验收标准

- 排版求解函数输出与上表完全一致
- 手机拍的照片能自动裁出符合国标比例的证件照，人脸居中
- 换蓝底后发丝边缘无明显白边（修补画笔可补救）
- 导出 PDF 物理尺寸精确为 102×152mm
- 实际打印后用尺子量，单张照片尺寸误差 < 0.5mm
- Windows 上双击 exe 能启动，全程不联网

## 相关

- [[Project/证件照处理/产品定位]]
