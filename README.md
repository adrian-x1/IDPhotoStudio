# ID Photo Studio

离线证件照制作工具。导入照片，自动抠图换底色，按标准规格裁剪排版，直接打印或导出。

全部处理都在本机完成，照片不会上传到任何服务器。

## 功能

- **自动裁剪**：识别人脸位置，按规格算好头顶留白和脸部占比，不用手动对齐。没检测到人脸时退回手动裁剪，可以拖拽、滚轮或方向键微调。
- **换底色**：白、蓝、红三种，也可以保持原底不动。
- **十种内置规格**：一寸、二寸、三寸、大一寸、小一寸、大二寸、小二寸、简历照、普通话水平测试、英语四六级。
- **自定义尺寸**：宽高各自独立输入，10–152mm。上限取 4R 相纸的长边，因为再大也排不进去。
- **6 寸相纸排版**：自动求解一张纸能排多少张，间距和边距可调（0–20mm），可选裁剪参考线。
- **导出与打印**：单张 JPEG / PNG，或整版相纸的 JPEG / PNG / PDF；也能直接调系统打印。

全部按 300 DPI 输出。

## 下载安装

到 [Releases](https://github.com/adrian-x1/IDPhotoStudio/releases) 页面下载对应平台的安装包。

### macOS（Apple Silicon）

下载 `IDPhotoStudio-x.y.z-macOS-arm64.dmg`，双击打开后把 ID Photo Studio 拖进「应用程序」文件夹。

首次打开会提示「无法验证开发者」，因为安装包没有做 Apple 代码签名。绕过方法：在「应用程序」里**右键点击**它，选「打开」，再在弹窗里确认「打开」。之后就能正常双击启动了。

如果右键仍被拦，去「系统设置 → 隐私与安全性」，在底部找到被阻止的提示，点「仍要打开」。

仅支持 M 系列芯片的 Mac。Intel Mac 暂不支持，因为依赖的 mediapipe 1.0.0 没有发布 macOS x86_64 版本。

### Windows（x64）

下载 `IDPhotoStudio-x.y.z-Windows-x64-Setup.exe`，双击一路下一步。安装需要管理员权限。

SmartScreen 可能提示「未知发布者」，点「更多信息 → 仍要运行」即可。同样是没做代码签名的缘故。

## 打印说明

用 EPSON L805 这类照片打印机时，驱动里的纸张类型必须选**光泽照片纸**。选普通纸会出现竖条纹和偏色。

## 命令行

`idphoto_cli.py` 提供一条最小的批处理通路，直接产出排好版的 4R 相纸 PNG：

```bash
python idphoto_cli.py 照片.jpg 一寸 白 --output-dir out
```

只支持内置规格，不支持自定义尺寸和直接打印——那些走图形界面。

## 从源码运行

需要 Python 3.13 x64。PySide6 6.9.3 不支持 3.14，装之前先确认版本。

```bash
git clone https://github.com/adrian-x1/IDPhotoStudio.git
cd IDPhotoStudio

python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 下载 170 MB 的抠图模型（太大不能进 git，会校验 SHA-256）
python scripts/fetch_models.py

python main.py
```

从源码运行时，macOS 上的文件选择框会是英文。这是 macOS 的规矩：对话框语言由**宿主程序**声明的本地化决定，源码运行时宿主是 Python 解释器，而它只声明支持英文。打包成 .app 之后身份换成本应用，就是中文了。

跑测试：

```bash
QT_QPA_PLATFORM=offscreen python -u scripts/run_tests.py
```

这个入口比 `python -m unittest discover -s tests` 多了一个看门狗：测试若卡住超过 7 分钟，会打印所有线程的调用栈再退出。CI 上的 stdout 是块缓冲的，没有它，一个死锁只会表现为二十几分钟的沉默，连卡在哪个测试都看不到。

## 自己打包

```bash
pip install -r requirements-build.txt
APP_VERSION=1.0.0 python -m PyInstaller --clean --noconfirm build.spec
```

`APP_VERSION` 会写进 macOS 的 `CFBundleShortVersionString`；不给就是 `0.0.0`。

macOS 再打 DMG：

```bash
bash scripts/make_dmg.sh v1.0.0
```

Windows 再打安装器（需要 [Inno Setup 6](https://jrsoftware.org/isdl.php)）：

```
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.0 installer\windows.iss
```

## 发布新版本

打一个 `v` 开头的 tag 推上去，GitHub Actions 会在 macOS 和 Windows 上各构建一次，跑完测试后把安装包挂到一个**草稿** Release 上：

```bash
git tag v1.0.0
git push origin v1.0.0
```

到 Releases 页面检查产物，补好说明，再点 Publish。

不想发版、只想验证构建能过，可以在 Actions 页面手动触发 Release 工作流，它会产出 artifact 但不创建 Release。

## 技术栈

- 抠图：ISNet（isnet-general-use），onnxruntime CPU 直接推理
- 人脸定位：MediaPipe FaceLandmarker
- 界面：PySide6

`core/` 里不含任何界面代码，可以脱离 GUI 单独测试——`grep -rn PySide6 core/` 应当无输出。毫米与像素的换算只有 `core/units.py` 一处，排版数量一律由 `solve_layout` 求解。
