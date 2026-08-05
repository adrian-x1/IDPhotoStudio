#!/bin/bash
# 从 Obsidian 库同步规划文档（库里是唯一事实源，这里只是副本）
V="/Users/lihongxia/Library/Mobile Documents/iCloud~md~obsidian/Documents/mind/Project/证件照处理"
cp "$V/开发规划.md" PLAN.md && cp "$V/产品定位.md" 产品定位.md && echo "已同步"
