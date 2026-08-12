# 开发说明

从源码运行、跑测试、自己打包、发布新版本。用户侧的下载与使用说明在 [README](../README.md)。

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

## 项目结构

```
core/       抠图、人脸检测、裁剪几何、排版求解、导出。不含任何界面代码
ui/         PySide6 界面：主窗口、裁剪视图、主题、抠图 worker、打印
tests/      单元测试，与 core/ 和 ui/ 的模块一一对应
scripts/    模型下载、测试入口、DMG 打包
assets/     应用图标与模型文件（.onnx 不进 git）
installer/  Inno Setup 的 Windows 安装器脚本
specs.json  内置证件照规格表
build.spec  PyInstaller 打包配置
```

两条一直守着的约定：

- `core/` 里不含任何界面代码，可以脱离 GUI 单独测试——`grep -rn PySide6 core/` 应当无输出。
- 毫米与像素的换算只有 `core/units.py` 一处，排版数量一律由 `core/layout.py` 的 `solve_layout` 求解。

## 跑测试

```bash
QT_QPA_PLATFORM=offscreen python -u scripts/run_tests.py
```

这个入口比 `python -m unittest discover -s tests` 多了一个看门狗：测试若卡住超过 7 分钟，会打印所有线程的调用栈再退出。CI 上的 stdout 是块缓冲的，没有它，一个死锁只会表现为二十几分钟的沉默，连卡在哪个测试都看不到。

`push` 和 `pull_request` 到 main 时，[CI 工作流](../.github/workflows/ci.yml)会在 macOS 与 Windows 上各跑一遍同样的命令。

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

到 Releases 页面检查产物，把变更写进 [CHANGELOG.md](../CHANGELOG.md) 和 Release 说明，再点 Publish。

不想发版、只想验证构建能过，可以在 Actions 页面手动触发 Release 工作流，它会产出 artifact 但不创建 Release。
