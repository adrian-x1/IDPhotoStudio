# 安全策略

## 支持范围

只有 [Releases](https://github.com/adrian-x1/IDPhotoStudio/releases/latest) 页面上的最新版本会收到安全修复。

## 这个应用做什么、不做什么

- 全部图像处理在本机完成，照片不会离开你的电脑。
- 运行时不联网，不上报任何遥测或使用数据。
- 只在**开发**时联网一次：`scripts/fetch_models.py` 从公网下载 170 MB 的抠图模型，并校验 SHA-256。安装包里模型是打包进去的，用户侧不会触发下载。
- 安装包没有做代码签名，所以 macOS 会提示「无法验证开发者」、Windows SmartScreen 会提示「未知发布者」。请只从本仓库的 Releases 页面下载，并核对文件名与大小。

## 报告漏洞

**不要开公开 Issue。**

请到 [Security → Report a vulnerability](https://github.com/adrian-x1/IDPhotoStudio/security/advisories/new) 私下提交，或直接邮件联系仓库所有者。请写清：

- 受影响的版本与操作系统
- 复现步骤
- 你判断的影响面

一周内会给回复。确认的问题修好后会在 Release 说明里致谢，除非你不希望被提及。
