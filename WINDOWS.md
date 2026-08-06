# idphoto：Mac 开发到 Windows 测试、打包与交付手册

这份手册只服务于当前 `idphoto` 项目。目标是把以后每次修改后的操作固定成同一条流水线，不再临时询问每一步。

## 先记住四件事

1. **代码在 Mac 上修改和提交，Windows 只负责真机测试、打包和打印验收。** PyInstaller 不能在 Mac 上生成可用的 Windows 程序。
2. **依赖文件在 Mac 上下载，Windows 从本地 wheel 文件夹离线安装。** Windows 仍需执行一次 `pip install`，但这个命令不会联网下载。
3. **离线依赖包和模型包通常只传一次。** 日常改代码只需要传新的源码压缩包。
4. **每次都创建全新的 `build` 和 `dist`。** 不复用旧打包结果，避免修改没有真正进入 EXE。

当前已验证过的链路使用 **64 位 Python 3.13**。现有离线包中的关键 wheel 是 `cp313-win_amd64`，不能给 Python 3.11、3.12、3.14 或 32 位 Python 使用。

> 仓库当前存在一处需要以后统一的文字冲突：`PLAN.md`、`requirements.txt` 和已有离线包按 Python 3.13 准备，但 `AGENTS.md` 仍写着 Python 3.11。在重新生成并验证整套 3.11 wheel 前，Windows 部署继续使用已经实际准备好的 3.13 链路；不要混装两个版本。

---

## 一、固定目录和三个传输包

### Mac 上的固定文件

```text
/Users/lihongxia/Projects/idphoto/                     项目源码
/Users/lihongxia/Projects/idphoto-windows-wheels.zip   Windows 离线依赖包
```

现有 `idphoto-windows-wheels.zip` 约 439 MB，内含 59 个 wheel 和一个 `INSTALL.txt`。它适用于 Windows x64 + CPython 3.13，并且不含 `onnxruntime-gpu`。

### Windows 上建议固定为

```text
C:\idphoto\
├─ offline\
│  ├─ windows-wheels\       解压后的离线 wheel，只准备一次
│  └─ models\               三个模型文件，只准备一次
├─ venv\                    公用 Python 虚拟环境，只创建一次
├─ source\                  本轮源码、测试和打包目录
└─ source-prev\             上一轮源码和打包结果，供回退
```

不要把项目放在桌面、微信接收目录、中文目录或带空格的目录。统一使用 `C:\idphoto`，后面的命令才能原样复制。

### 三种压缩包的用途

| 压缩包 | 何时传到 Windows | 是否每次重做 |
|---|---|---|
| `idphoto-windows-wheels.zip` | 第一次部署；依赖版本变化后 | 否 |
| `idphoto-windows-models.zip` | 第一次部署；模型变化后 | 否 |
| `idphoto-source-日期时间.zip` | 每轮 Mac 修改完成后 | 是 |

---

## 二、第一次准备：在 Mac 上生成离线材料

这一章通常只做一次。已经有可用的 wheel 和模型包时，直接跳到第三章。

### 2.1 检查已有离线 wheel 包

在 Mac 终端执行：

```bash
unzip -t /Users/lihongxia/Projects/idphoto-windows-wheels.zip
```

最后应看到：

```text
No errors detected in compressed data
```

再确认它没有 GPU 版 ONNX Runtime：

```bash
unzip -l /Users/lihongxia/Projects/idphoto-windows-wheels.zip | grep -i onnxruntime
```

应只有类似下面的一项，不能出现 `onnxruntime-gpu`：

```text
onnxruntime-1.23.2-cp313-cp313-win_amd64.whl
```

### 2.2 生成独立模型包

模型不常变化，单独传一次可避免每轮重复传输约 174 MB 的 ONNX 文件。

```bash
cd /Users/lihongxia/Projects/idphoto
zip -j /Users/lihongxia/Projects/idphoto-windows-models.zip \
  assets/models/isnet-general-use.onnx \
  assets/models/face_landmarker.task \
  assets/models/blaze_face_short_range.tflite
unzip -t /Users/lihongxia/Projects/idphoto-windows-models.zip
```

模型包内必须有这三个精确文件名：

```text
isnet-general-use.onnx
face_landmarker.task
blaze_face_short_range.tflite
```

其中 `isnet-general-use.onnx` 约 170 MB，`face_landmarker.task` 约 3.6 MB。文件被改名、缺失或放错目录，都可能导致程序尝试联网下载或直接报错。

### 2.3 只有依赖变化时，才重新生成 wheel 包

满足任意一项才需要重做：

- `requirements.txt` 发生变化；
- `requirements-build.txt` 发生变化；
- Python 主次版本发生变化；
- Windows 架构不再是 x64；
- 离线安装提示某个 wheel 缺失。

在 Mac 上执行下面的命令。它只下载 Windows x64 / Python 3.13 的二进制 wheel，不在 Mac 环境中安装这些 Windows 包：

```bash
cd /Users/lihongxia/Projects/idphoto
IDPHOTO_WHEEL_TMP=$(mktemp -d)

.venv/bin/python -m pip download \
  --dest "$IDPHOTO_WHEEL_TMP/windows-wheels" \
  --platform win_amd64 \
  --python-version 3.13 \
  --implementation cp \
  --abi cp313 \
  --only-binary=:all: \
  -r requirements.txt \
  -r requirements-build.txt

.venv/bin/python -m pip download \
  --dest "$IDPHOTO_WHEEL_TMP/windows-wheels" \
  --platform win_amd64 \
  --python-version 3.13 \
  --implementation cp \
  --abi cp313 \
  --only-binary=:all: \
  pefile pywin32-ctypes colorama pyreadline3

cd "$IDPHOTO_WHEEL_TMP"
zip -r /Users/lihongxia/Projects/idphoto-windows-wheels-new.zip windows-wheels
unzip -t /Users/lihongxia/Projects/idphoto-windows-wheels-new.zip
```

先把 `idphoto-windows-wheels-new.zip` 拿到 Windows 按第三章完整验证。验证成功后，它才能替换旧包；不要先覆盖当前可用的 `idphoto-windows-wheels.zip`。

### 2.4 Python 安装器

Windows 第一次部署还需要一份官方 **Python 3.13 64-bit Windows installer**。如果 Windows 不能联网，就在 Mac 下载 `.exe` 后和两个离线包一起传过去。安装器只需使用一次，之后不要反复重装 Python。

---

## 三、第一次准备：Windows 基础环境

本章只做一次。所有命令都在 Windows 的“命令提示符（CMD）”中执行，不使用 PowerShell 激活虚拟环境。

### 3.1 安装 Python 3.13 x64

运行 Python 安装器，第一页勾选：

```text
Add python.exe to PATH
```

安装完成后关闭旧 CMD，重新打开一个 CMD，执行：

```bat
python --version
```

预期输出以此开头：

```text
Python 3.13
```

再确认是 64 位：

```bat
python -c "import struct; print(struct.calcsize('P') * 8)"
```

预期输出：

```text
64
```

任一结果不对都先停止，不要继续创建虚拟环境。

### 3.2 解压离线包

1. 新建 `C:\idphoto\offline`。
2. 把 `idphoto-windows-wheels.zip` 完整解压到 `C:\idphoto\offline`。
3. 把 `idphoto-windows-models.zip` 完整解压到 `C:\idphoto\offline\models`。

完成后应存在：

```text
C:\idphoto\offline\windows-wheels\
C:\idphoto\offline\models\isnet-general-use.onnx
C:\idphoto\offline\models\face_landmarker.task
C:\idphoto\offline\models\blaze_face_short_range.tflite
```

注意不要得到双层目录，例如：

```text
C:\idphoto\offline\windows-wheels\windows-wheels\
```

如果出现双层目录，把内层 `windows-wheels` 移到 `C:\idphoto\offline`。

### 3.3 第一次放入源码

把最新 `idphoto-source-日期时间.zip` 解压。压缩包里会有一个 `idphoto` 文件夹，把它改名并放到：

```text
C:\idphoto\source
```

确认下列文件存在：

```text
C:\idphoto\source\main.py
C:\idphoto\source\requirements.txt
C:\idphoto\source\requirements-build.txt
C:\idphoto\source\build.spec
```

### 3.4 创建公用虚拟环境

在 CMD 中逐条执行：

```bat
cd /d C:\idphoto
python -m venv venv
C:\idphoto\venv\Scripts\activate.bat
```

成功后，命令行最前面应出现：

```text
(venv)
```

以后每次重新打开 CMD，都只需重新执行激活命令，不需要重建虚拟环境。

### 3.5 从本地 wheel 离线安装依赖

```bat
cd /d C:\idphoto\source
python -m pip install --no-index --find-links=C:\idphoto\offline\windows-wheels -r requirements.txt -r requirements-build.txt
```

这里的 `--no-index` 表示禁止访问在线软件源。命令只能从 Mac 准备的 `windows-wheels` 文件夹安装。

安装结束后执行：

```bat
python -m pip check
```

预期输出：

```text
No broken requirements found.
```

再检查关键依赖：

```bat
python -m pip list | findstr /I "mediapipe rembg onnxruntime opencv pillow numpy PySide6 pyinstaller"
```

应能看到当前锁定版本：

| 包 | 版本 |
|---|---:|
| mediapipe | 1.0.0 |
| rembg | 2.0.77 |
| onnxruntime | 1.23.2 |
| opencv-contrib-python | 5.0.0.93 |
| pillow | 12.3.0 |
| numpy | 2.3.5 |
| PySide6 | 6.9.3 |
| pyinstaller | 6.21.0 |

ONNX Runtime 只能有 `onnxruntime`，绝不能出现 `onnxruntime-gpu`。

### 3.6 复制模型并检查导入

```bat
cd /d C:\idphoto\source
copy /Y C:\idphoto\offline\models\* assets\models\
python -c "import mediapipe, onnxruntime, PySide6, rembg, pymatting; print('IMPORT_OK')"
```

预期最后输出：

```text
IMPORT_OK
```

第一次基础环境到这里完成。

---

## 四、每次修改后的固定日常流程

以后每次只做本章。完整顺序是：

```text
Mac 测试并提交
    ↓
Mac 生成小型源码 ZIP
    ↓
Windows 保留上一版，换入新源码
    ↓
Windows 离线同步依赖、运行测试
    ↓
Windows 清理后重新打包
    ↓
Windows 功能、断网、导出和打印验收
```

### 4.1 Mac：先验证代码

```bash
cd /Users/lihongxia/Projects/idphoto
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
git diff --check
git status --short
```

通过标准：

- 测试最后显示 `OK`；
- `git diff --check` 没有输出；
- `git status --short` 没有输出，表示本轮修改已经提交且工作区干净。

任何一项不满足都不要传 Windows。先在 Mac 修复并提交。

### 4.2 Mac：生成本轮源码压缩包

下面的包排除 `.git`、Mac 虚拟环境、测试照片、旧构建结果和 170 MB ONNX 模型。大模型会在 Windows 从固定的 `offline\models` 复制回来。

```bash
cd /Users/lihongxia/Projects
IDPHOTO_STAMP=$(date +%Y%m%d-%H%M)
IDPHOTO_SOURCE_ZIP="/Users/lihongxia/Projects/idphoto-source-${IDPHOTO_STAMP}.zip"

zip -r "$IDPHOTO_SOURCE_ZIP" idphoto \
  -x "idphoto/.git/*" \
     "idphoto/.venv/*" \
     "idphoto/__pycache__/*" \
     "idphoto/*/__pycache__/*" \
     "idphoto/build/*" \
     "idphoto/dist/*" \
     "idphoto/out/*" \
     "idphoto/samples/*" \
     "idphoto/.DS_Store" \
     "idphoto/assets/models/isnet-general-use.onnx" \
     "idphoto/*.zip"

unzip -t "$IDPHOTO_SOURCE_ZIP"
echo "$IDPHOTO_SOURCE_ZIP"
```

最后两项检查：

```bash
unzip -l "$IDPHOTO_SOURCE_ZIP" | grep -E "main.py|build.spec|requirements.txt|requirements-build.txt|face_landmarker.task"
unzip -l "$IDPHOTO_SOURCE_ZIP" | grep "isnet-general-use.onnx"
```

第一条应列出关键文件；第二条应该**没有输出**，因为大模型不会重复放进源码包。

本轮只需把这个新的源码 ZIP 传到 Windows。依赖和模型没变化时，不要重传两个大离线包。

### 4.3 Windows：安全换入新源码

先关闭正在运行的 `idphoto.exe`，再打开 CMD。确保当前目录不在旧 `source` 内，然后执行：

```bat
cd /d C:\idphoto
if exist source-prev rmdir /S /Q C:\idphoto\source-prev
if exist source ren source source-prev
```

这两条命令只删除上上轮备份，并把上一轮改名为 `source-prev`。刚刚能运行的上一版仍然保留，可随时回退。

然后用资源管理器解压新的 `idphoto-source-日期时间.zip`，把其中的 `idphoto` 文件夹移动到：

```text
C:\idphoto\source
```

不要直接把新文件覆盖到旧 `source`，否则已经从 Mac 删除的旧文件可能残留并进入打包结果。

### 4.4 Windows：激活环境、补模型、同步依赖

```bat
C:\idphoto\venv\Scripts\activate.bat
cd /d C:\idphoto\source
python --version
copy /Y C:\idphoto\offline\models\* assets\models\
python -m pip install --no-index --find-links=C:\idphoto\offline\windows-wheels -r requirements.txt -r requirements-build.txt
python -m pip check
```

预期：

- Python 显示 3.13；
- 三个模型显示已复制；
- 依赖未变化时，多数包显示 `Requirement already satisfied`，很快结束；
- `pip check` 显示 `No broken requirements found.`。

每轮都运行离线安装命令没有问题。它不会联网，也不会重复下载；这样即使某次依赖文件发生变化，也不会被遗漏。

### 4.5 Windows：打包前测试

```bat
set QT_QPA_PLATFORM=offscreen
python -m unittest discover -s tests -v
set QT_QPA_PLATFORM=
```

最后必须显示：

```text
OK
```

如果显示 `FAILED` 或 `ERROR`，停止，不要打包。把失败测试名、完整报错和刚执行的命令发给 AI。

### 4.6 Windows：清理并重新打包

下面两条删除的目标只能是当前源码目录里的 `build` 和 `dist`。先用 `cd` 和 `dir` 确认位置，再执行：

```bat
cd /d C:\idphoto\source
dir
if exist build rmdir /S /Q build
if exist dist rmdir /S /Q dist
python -m PyInstaller --clean --noconfirm build.spec
```

成功标志：命令退出前没有 traceback，并且存在：

```text
C:\idphoto\source\dist\idphoto\idphoto.exe
```

用命令确认：

```bat
if exist dist\idphoto\idphoto.exe (echo BUILD_OK) else (echo BUILD_FAILED)
```

预期输出：

```text
BUILD_OK
```

这是 **onedir** 程序。`idphoto.exe` 必须和旁边的 `_internal` 等文件一起使用，绝不能只复制一个 EXE。

### 4.7 Windows：先联网运行，再做断网验证

从 CMD 启动：

```bat
cd /d C:\idphoto\source
dist\idphoto\idphoto.exe
```

先完成一轮基础功能测试：

1. 软件能正常打开，无黑屏、闪退或错误弹窗；
2. 导入一张有人脸的 JPG；
3. 自动出现固定比例裁剪框；
4. 拖动框、拖四角、滚轮缩放都正常；
5. 切换规格，右侧张数和排版立即更新；
6. “保持原底”正常；
7. 白、蓝、红背景都能完成处理；
8. PNG 和 PDF 都能导出并打开。

再关闭软件，断开 Wi-Fi 和网线，重新启动同一个 EXE：

1. 导入照片，确认 `face_landmarker.task` 能离线加载；
2. 切换白、蓝或红底，确认 `isnet-general-use.onnx` 能离线加载；
3. 不能出现下载提示、联网失败或模型缺失错误。

只有这三项完成，才能写“离线模型加载已验证”。仅在联网状态运行成功，不能当作离线验证。

### 4.8 Windows：按改动范围做验收

不是每次都需要真实打印，但改到相关模块时必须做对应检查：

| 本轮改动 | Windows 必测内容 |
|---|---|
| `core/detect.py`、模型 | 多张不同照片的人脸检测、断网加载 |
| `core/crop.py`、`ui/crop_view.py` | 自动框、移动、四角缩放、滚轮、边界夹取 |
| `core/matting.py`、换底线程 | 原底、白底、蓝底、红底、连续切换 |
| `core/layout.py`、`specs.json` | 规格、张数、横竖排版、间距、边距、裁剪线 |
| `core/export.py` | PNG、PDF 均能打开，尺寸和清晰度正确 |
| `ui/printing.py`、打印设置 | 必须真实打印并用尺测量 |
| `build.spec`、依赖、资源路径 | 必须清理重打包并断网运行 EXE |
| 只改普通界面文字或样式 | 完整打开、导入和基础操作即可 |

### 4.9 Windows：打印与物理尺寸验收

软件和打印机驱动都选择 4R（102 × 152 mm）相纸。驱动里关闭：

- “适应纸张”“适合页面”或同类自动缩放；
- “无边距缩放”或同类自动放大。

打印后用毫米尺测量其中一张照片的宽、高，与软件所选规格比较。宽和高的绝对误差都应小于 0.5 mm。任一方向超差都不能通过，应先检查驱动缩放设置。

如果直接打印不稳定，先导出 PDF，再用系统 PDF 工具按“实际大小 / 100%”打印，不要选择“适合页面”。

---

## 五、交付 Windows 成品

完成测试后，要压缩的是整个 `dist\idphoto` 文件夹，而不是单个 EXE。

在 CMD 中执行：

```bat
cd /d C:\idphoto\source
powershell -NoProfile -Command "Compress-Archive -Path 'dist\idphoto' -DestinationPath 'idphoto-Windows.zip' -Force"
```

这里只是从 CMD 调用 Windows 自带压缩功能，不需要进入 PowerShell，也不涉及虚拟环境激活策略。

把 `idphoto-Windows.zip` 解压到一个新的临时目录，再从新目录运行一次 `idphoto.exe`。这一步用于发现“开发目录能运行，但交付 ZIP 漏文件”的问题。

正式交付时附上以下记录：

```text
Mac 提交：<git commit 短哈希>
源码包：idphoto-source-<日期时间>.zip
Windows 系统：<Windows 版本>
Python：3.13.x 64-bit
Windows 测试：通过 / 未通过
Windows 打包：通过 / 未通过
离线模型：通过 / 未验证
PNG/PDF：通过 / 未验证
真实打印：通过 / 未验证
成品包：idphoto-Windows.zip
```

---

## 六、失败时怎么处理

### 6.1 `python` 不是 3.13

执行：

```bat
where python
python --version
C:\idphoto\venv\Scripts\python.exe --version
```

日常命令应先激活 `C:\idphoto\venv`。如果公用虚拟环境本身不是 3.13，不要在里面硬修；把它改名保留，再用正确的 Python 3.13 重建。

### 6.2 离线安装提示 `No matching distribution found`

常见原因：

- wheel ZIP 没有完整解压；
- `--find-links` 路径多了一层 `windows-wheels`；
- Python 不是 3.13 x64；
- `requirements*.txt` 已更新，但 wheel 包还是旧版。

先执行：

```bat
dir C:\idphoto\offline\windows-wheels
python --version
python -c "import struct; print(struct.calcsize('P') * 8)"
```

不要删包碰运气，也不要临时取消 `--no-index` 联网混装。确认缺少哪个 wheel 后，回 Mac 重做离线包。

### 6.3 `onnxruntime_pybind11_state` 或 `DLL load failed`

先确认没有 GPU 版：

```bat
python -m pip list | findstr /I onnxruntime
```

结果只能有一行 `onnxruntime 1.23.2`。如果出现 `onnxruntime-gpu`，说明环境已被污染，应重建 `C:\idphoto\venv`，不要继续在原环境叠加安装。

如果只有 CPU 版仍报 DLL 错误，再检查 Windows 是否安装了 Microsoft Visual C++ 2015–2022 x64 Runtime。目标机器离线时，也应在 Mac 下载官方 x64 安装器后传入；不要从第三方 DLL 网站单独下载 DLL。

### 6.4 `PackageNotFoundError: No package metadata was found for pymatting`

这表示打包结果缺少 `pymatting` 的 `.dist-info` 元数据。当前 `build.spec` 已通过下面的配置修复：

```python
copy_metadata("pymatting")
```

确认本轮源码里有这行，然后删除旧 `build`、`dist`，重新执行：

```bat
python -m PyInstaller --clean --noconfirm build.spec
```

Mac 测试通过不等于 Windows EXE 已修复，必须运行 Windows 重新生成的 EXE 才算验证。

### 6.5 软件尝试下载模型或提示模型不存在

确认：

```bat
dir C:\idphoto\source\assets\models
dir C:\idphoto\source\dist\idphoto\_internal\assets\models
```

两处都应有三个模型。尤其检查：

```text
isnet-general-use.onnx
```

文件名必须完全一致；不能改名成 `isnet-general-use (1).onnx`。`U2NET_HOME` 指向模型目录，不是模型文件。

### 6.6 修改后运行起来还是旧效果

按顺序检查：

1. Windows 换入的是最新源码 ZIP；
2. 当前目录是 `C:\idphoto\source`；
3. 旧 `build` 和 `dist` 已删除；
4. 使用的是 `python -m PyInstaller ...`，且虚拟环境已激活；
5. 运行的是本轮 `C:\idphoto\source\dist\idphoto\idphoto.exe`，不是桌面旧快捷方式。

### 6.7 EXE 闪退、看不到错误

先在源码模式运行：

```bat
cd /d C:\idphoto\source
C:\idphoto\venv\Scripts\activate.bat
python main.py
```

如果源码能运行、只有 EXE 失败，问题通常在打包资源或 hidden import。需要查看冻结程序错误时，可以临时把 `build.spec` 的 `console=False` 改为 `console=True` 后清理重打包，再从 CMD 运行 EXE。排错结束必须改回 `console=False`，再次清理并生成正式包；临时调试修改不要传回 Mac 或提交。

### 6.8 立即回退上一版

如果本轮新版本失败，可在关闭软件后执行：

```bat
cd /d C:\idphoto
ren source source-failed
ren source-prev source
```

上一轮的源码、`dist` 和 EXE 会一起恢复。失败版先保留，等日志和原因确认后再处理。

---

## 七、向 AI 报错时一次性提供这些信息

不要只发“打不开”或一张截断的截图。复制下面模板，把命令和从第一行到最后一行的完整输出一起发出：

```text
我正在执行 WINDOWS.md 第 <章节号> 步。
本轮 Mac commit：<短哈希>
Windows 版本：<winver 显示内容>
执行的命令：<原样粘贴>
完整输出：
<从命令开始到 CMD 提示符重新出现的全部文字>

python --version：
<输出>

python -m pip check：
<输出>

python -m pip list | findstr /I "mediapipe rembg onnxruntime PySide6 pyinstaller pymatting"：
<输出>

源码运行 python main.py：成功 / 失败 / 未测试
EXE 运行：成功 / 失败 / 未测试
联网状态：联网 / 已断网
```

有了这组信息，AI 可以直接判断是源码、依赖、模型、PyInstaller 还是打印机驱动问题，不必重新从第一步问起。

---

## 八、最短版检查清单

### 每轮 Mac

- [ ] 完整测试 `OK`
- [ ] `git diff --check` 通过
- [ ] 修改已提交，`git status --short` 为空
- [ ] 生成并验证新的源码 ZIP
- [ ] 只传源码 ZIP；依赖或模型变化时才重传大包

### 每轮 Windows

- [ ] 关闭旧程序，上一版改名为 `source-prev`
- [ ] 新源码放到 `C:\idphoto\source`
- [ ] 激活 `C:\idphoto\venv`
- [ ] 从 `offline\models` 复制模型
- [ ] 使用 `--no-index` 同步离线依赖
- [ ] `pip check` 通过
- [ ] Windows 测试 `OK`
- [ ] 删除当前 `build`、`dist`
- [ ] PyInstaller 重新打包并显示 `BUILD_OK`
- [ ] EXE 基础功能通过
- [ ] 断网模型验证通过，或明确记录“未验证”
- [ ] 涉及打印时完成真实打印和尺量
- [ ] 压缩整个 `dist\idphoto`，解压后再运行一次
