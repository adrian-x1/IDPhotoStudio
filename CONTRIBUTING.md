# 参与贡献

欢迎提 Issue 和 Pull Request。

## 报告问题

- **用起来不对** — 提 [Bug 报告](https://github.com/adrian-x1/IDPhotoStudio/issues/new?template=bug_report.yml)，带上系统版本、应用版本和复现步骤。裁剪或排版不对的话，附一张截图最省事。
- **想要新功能** — 提 [功能建议](https://github.com/adrian-x1/IDPhotoStudio/issues/new?template=feature_request.yml)，说清用它解决什么问题，而不只是要什么控件。
- **安全问题** — 别开公开 Issue，走 [SECURITY.md](SECURITY.md) 里的流程。

## 改代码

环境搭建、跑测试、打包，全在 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

提 PR 前请确认：

1. **测试全绿** — `QT_QPA_PLATFORM=offscreen python -u scripts/run_tests.py`
2. **改动带测试** — `tests/` 与 `core/`、`ui/` 的模块一一对应，新行为要有对应断言
3. **`core/` 不碰界面** — `grep -rn PySide6 core/` 必须无输出。`core/` 要能脱离 GUI 单独测试
4. **换算与求解不另开一处** — 毫米像素换算只在 `core/units.py`，排版数量一律走 `core/layout.py` 的 `solve_layout`。不要在别处写死数字或重算一遍

## 提交信息

用中文祈使句，一行说清做了什么，不写 `fix:`、`feat:` 这类前缀。正文说清**为什么**这么改——踩了什么坑、试过什么别的方案、实测数据是多少。仓库现有历史就是范例，随便挑一条看看（下面是节选）：

```
修复自定义尺寸输入框吞按键与静默截断

自定义宽高框此前用 specialValueText 表示未填写、用 range 上界兜合法性，
两者都会让 QDoubleSpinBox 的 validator 直接吞掉按键：

- 鼠标点进空框（显示 "--"）后打字全部被拒，文本始终是 "--"，无任何反馈
- 超上限的输入被逐字符截断后当成合法值提交：160 变 16、200 变 20 ……

改为 CustomSizeSpinBox：range 放宽到不参与合法性判定，上下限只由
_commit_custom_dimension 裁决 ……

原有测试用 setValue + editingFinished.emit 绕过了 validator 和焦点系统，
四个缺陷因此全部逃逸，补六个走 QTest 真实鼠标与按键的回归用例。
```

一个提交只做一件事。界面观感的微调可以合成一条，功能与重构分开。
