## 改了什么

<!-- 一句话说清这个 PR 做了什么。关联的 Issue 写成 Fixes #123 -->

## 为什么这么改

<!-- 踩了什么坑、试过什么别的方案、实测数据是多少 -->

## 自测清单

- [ ] `QT_QPA_PLATFORM=offscreen python -u scripts/run_tests.py` 全绿
- [ ] 新行为有对应测试
- [ ] `grep -rn PySide6 core/` 无输出
- [ ] 没有在 `core/units.py` 之外新写毫米像素换算，排版数量仍走 `solve_layout`
- [ ] 改了界面的话，附了改动前后的截图
