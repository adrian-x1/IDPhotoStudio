# Windows 部署说明

以下命令都在解压后的项目目录中执行。PyInstaller 不是跨平台编译器，Windows 程序必须在 Windows 上构建，不能复制 Mac 的 Python 环境。

## 1. 安装 Python 3.13

从 Python 官网安装 64 位 Python 3.13。不要安装 Python 3.14。

安装器第一页必须勾选 **Add python.exe to PATH**。安装后打开新的“命令提示符”，确认版本：

```bat
python --version
```

输出必须以 `Python 3.13` 开头，否则先修正 Python 安装或 PATH，再继续。

## 2. 创建虚拟环境并安装依赖

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-build.txt
```

每次重新打开命令提示符后，都要先进入项目目录并执行：

```bat
.venv\Scripts\activate
```

## 3. 检查 ONNX Runtime

环境里只能安装 `onnxruntime`，绝对不能安装 `onnxruntime-gpu`。两者共存会导致 `DLL load failed while importing onnxruntime_pybind11_state`；这台机器的 AMD 显卡也不能使用 CUDA 版。

```bat
pip list | findstr onnxruntime
```

结果只能有一行 `onnxruntime 1.23.2`。如果出现 `onnxruntime-gpu`，停止构建，删除 `.venv` 后按第 2 步重新创建干净环境。

## 4. 可选：运行人脸检测测试

`tests/test_detect.py` 要求 `samples\` 下至少有 3 张 JPG。少于 3 张时测试会失败，不会跳过；`samples\` 和其中照片不会提交到 Git。

准备好样片后运行：

```bat
python -m unittest discover -s tests -p "test_detect.py" -v
```

## 5. 构建 onedir 程序

确认两个模型文件都在 `assets\models\` 后执行：

```bat
pyinstaller build.spec
```

程序入口是：

```text
dist\idphoto\idphoto.exe
```

这是 onedir 程序。复制或压缩部署时必须保留整个 `dist\idphoto\` 目录，不能只复制 `idphoto.exe`。

### 看不到报错时

最终配置是 `build.spec` 中的 `console=False`，正常启动不会出现黑色控制台窗口。首次在 Windows 上排错时，可以临时改成 `console=True`，重新执行 `pyinstaller build.spec`，再从命令提示符运行 `dist\idphoto\idphoto.exe` 查看错误。

问题排除后必须把它改回 `console=False`，删除旧的 `build\` 和 `dist\`，然后重新执行 `pyinstaller build.spec` 生成正式版本。

## 6. 断网验证两个模型

构建完成后断开 Wi-Fi 和网线，再运行 `dist\idphoto\idphoto.exe`：

1. 导入一张有人脸的照片，确认能自动出现裁剪框。这会加载 `blaze_face_short_range.tflite`。
2. 把底色从“保持原底”切换为白、蓝或红，等待换底结果出现。这会加载 `isnet-general-use.onnx`。
3. 两步都不能出现下载提示、联网失败或模型缺失错误。

## 7. 打印与尺寸验收

在软件和打印机驱动中选择 4R（102 × 152 mm）相纸。打印前在打印机驱动里关闭：

- “适应纸张”“适合页面”或同类自动缩放选项；
- “无边距缩放”或同类自动放大选项。

打印一张后，用毫米尺测量其中一张照片的宽和高，并分别与软件所选规格的毫米尺寸比较。宽、高的绝对误差都必须小于 0.5 mm；任一方向超差都不能通过验收，应先检查驱动缩放设置。
