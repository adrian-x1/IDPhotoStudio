# 变更记录

本文件记录每个版本的显著变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

安装包在 [Releases](https://github.com/adrian-x1/IDPhotoStudio/releases) 页面下载。

## [v0.3.0] — 2026-08-10

### 新增

- 自定义证件照尺寸：宽高各自独立输入，10–152mm，上限取 4R 相纸的长边
- 自定义尺寸的排版边界求解与超限时的错误提示样式

### 变更

- 文件选择对话框与 Qt 内置文本改为中文
- macOS 应用包只声明中文本地化，非中文系统下也能拿到中文访达对话框
- 窗口标题与 `CFBundleName` 统一为 ID Photo Studio 字标
- 分段控件改为自绘单选，避免平台差异；数量标签可容纳三位数
- 放大间距与边距的重置旋钮，恢复默认按钮移到它所管的参数旁
- 启动时焦点不再落在间距输入框
- 测试改由带看门狗的入口 `scripts/run_tests.py` 运行，卡住时会打印所有线程的调用栈

### 修复

- 自定义尺寸输入框吞按键与静默截断
- 自定义尺寸框内二次点击改为定位光标，允许逐位编辑
- Windows 打包链路的 Qt 翻译文件路径与应用版本号
- macOS CI 挂死：某个测试泄漏的真实抠图 worker 会饿死后续测试

## [v0.2.0] — 2026-08-08

### 变更

- 抠图改用 onnxruntime 直接推理，移除 rembg 依赖链

### 修复

- 打包后单选按钮出现原生蓝色圆圈
- 旋转按钮残留选中态，且旋转后无法重置

## [v0.1.0] — 2026-08-08

首个发布版本，提供完整的证件照制作通路：

- MediaPipe FaceLandmarker 人脸定位，按规格反解头顶留白与脸部占比的两参数裁剪几何
- ISNet 离线抠图换底，支持白、蓝、红与保持原底
- 十种内置规格，6 寸相纸排版求解，间距与边距可调，可选裁剪参考线
- 可拖拽缩放的裁剪框，照片与裁剪框独立旋转，横竖版切换
- 单张与整版相纸的 JPEG / PNG / PDF 导出，以及直接调用系统打印
- `idphoto_cli.py` 命令行批处理通路
- macOS 与 Windows 双平台自动构建与发布流程

[v0.3.0]: https://github.com/adrian-x1/IDPhotoStudio/releases/tag/v0.3.0
[v0.2.0]: https://github.com/adrian-x1/IDPhotoStudio/releases/tag/v0.2.0
[v0.1.0]: https://github.com/adrian-x1/IDPhotoStudio/releases/tag/v0.1.0
