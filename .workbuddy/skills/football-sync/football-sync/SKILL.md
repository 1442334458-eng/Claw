---
name: football-sync
description: 足球分析三阶段自动同步 — 分析前 pull 拉取最新数据，分析后 push 推送报告，复盘后 push 推送新经验。在足球竞彩/比赛分析/投注方案/赛后复盘等场景自动加载。
version: 1.3.0
agent_created: true
created: 2026-08-09
updated: 2026-08-09
tags: [足球, 同步, Git, GitHub, 双机, 复盘]
---

# 足球分析三阶段双机同步技能

## 触发条件

> **此技能的核心价值**：确保两台电脑（Surface / xieyu）的足球分析数据（lessons.md、铁律、pipeline代码）始终保持同步。不加载此技能 = 可能用过期数据做分析 = 白分析。

当用户进行以下操作时，**必须先加载此技能**，再加载足球分析技能：
- 发送竞彩截图、要求分析足球比赛
- 请求足球投注方案、赔率分析、盘口解读
- 请求比赛预测、球队对比、晋级概率
- 任何涉及 football-betting-analysis / football-match-analysis / football-pipeline-v8 的场景
- **赛后复盘、命中率统计、经验回写 lessons.md**

## 三个触发时机

| 时机 | 命令 | 原因 |
|------|------|------|
| ① 分析前 | `pull` | 拉取另一台电脑的最新 lessons.md 和数据，避免用过期经验 |
| ② 分析后 | `push` | 推送报告、方案、技能更新到 GitHub |
| ③ 复盘后 | `push` | 推送新写入的经验教训到 lessons.md，确保下次分析能用上 |

## 铁律①：分析前自动 Pull（时效检查）

> **时效检查机制**：`git-sync.py` 在每次 pull 后写入 `.last_pull_time` 时间戳。
> 分析前执行 pull 时，git-sync 通过 GitHub API 获取远端最新 commit 时间，与时间戳对比：
> - 如果远端无新 commit → 跳过，0.5 秒结束
> - 如果远端有新 commit 但本地 pull 不超过 2 小时 → 提示用户"数据很新"，可选跳过
> - 如果远端有新 commit 且超过 2 小时 → 执行全量 pull，告知同步内容

**分析开始时必须执行：**

```bash
python3 "$(cygpath -m "$HOME")/.workbuddy/skills/git-sync.py" pull
```

> `cygpath -m "$HOME"` 在 Git Bash 中自动转换为各机器的正确 Windows 路径，两台电脑通用。

执行流程：
1. 运行 pull 命令
2. 如果三个仓库都显示「文件列表一致 / Pull 完成」且无实际下载 → 直接跳过，继续分析
3. 如果有文件被更新 → 告知用户「从另一台电脑同步了 X 条新经验」
4. 如果 pull 失败（网络问题）→ 静默跳过，用本地数据继续分析
5. 如果距离上次自动 pull 不到 2 小时 → 可以跳过此步（数据足够新鲜）

**不需要每次都全量拉取。** 自动化的存在让分析前 pull 成为「保险」而非「前提」。

## 铁律②：分析后必须 Push

**在足球分析完成、报告交付给用户之后，必须执行：**

```bash
python3 "$(cygpath -m "$HOME")/.workbuddy/skills/git-sync.py" push
```

执行流程：
1. 分析报告已生成并交付给用户
2. 运行 push 命令
3. 检查输出，确认推送成功
4. 如果 push 失败，告知用户稍后手动推送
5. 如果分析过程中没有修改任何技能文件（纯对话无文件变更），可跳过 push

**必须 push 的情况：**
- lessons.md 更新了经验教训
- 数据文件有新增或修改
- SKILL.md 有任何改动
- 任何 .py / .json / .md 文件被写入或修改

## 铁律③：复盘后必须 Push

**在赛后复盘完成、经验回写 lessons.md 之后，必须执行：**

```bash
python3 "$(cygpath -m "$HOME")/.workbuddy/skills/git-sync.py" push
```

执行流程：
1. 复盘猿完成四维命中率统计（方向/比分/让球/半全场）
2. 盈亏计算完成
3. 新经验已写入 lessons.md（命中规律/失误教训/新规则）
4. 运行 push 命令
5. 检查输出，确认推送成功

**复盘后 push 的核心价值：**
- 今天发现的新规律（如 DOIT 0.596 信号验证、PFI 疲劳影响修正）立即同步到云端
- 另一台电脑下次分析时 pull 即可获得最新经验
- 避免两台电脑的 lessons.md 产生分叉

**必须 push 的情况：**
- lessons.md 新增了命中/失误记录
- 复盘发现需要新增/修改铁律
- 复盘报告文件已生成
- 任何命中率统计数据被写入

## 快速状态检查

如果用户想确认两台电脑的数据是否同步，运行：

```bash
python3 "$(cygpath -m "$HOME")/.workbuddy/skills/git-sync.py" status
```

## 技术说明

- `git-sync.py` 通过 GitHub API（api.github.com）同步，不依赖 github.com:443
- Token 已内置在脚本中，无需额外配置
- 三个仓库均为私有：football-betting-analysis / football-match-analysis / football-pipeline-v8
- 此技能文件本身通过 Git + GitHub 同步到两台电脑（`git-sync.py push/pull`），不再依赖 Syncthing
- 路径使用 `$(cygpath -m "$HOME")` 自动适配两台电脑的用户名差异，无需手动修改
- **并发安全**：两台电脑同时 pull 完全无冲突（纯读取）；同时 push 概率极低且 GitHub API 会自动拒绝后到达的 push，数据不会损坏

## 版本变更

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0.0 | 2026-08-09 | 初版，三阶段同步（pull → push → push），路径硬编码 `C:/Users/xieyu/` |
| v1.1.0 | 2026-08-09 | 旧电脑升级：新增铁律③复盘后push、快速状态检查、技术说明 |
| v1.1.1 | 2026-08-09 | 修复双机路径兼容：`cygpath -m "$HOME"` 替代硬编码 `xieyu`；清理过时 Syncthing 说明 |
| v1.2.0 | 2026-08-09 | 分析前 pull 降级为「快速检查」+ 新增 2 小时窗口跳过规则 + 并发安全说明 |
| v1.2.1 | 2026-08-09 | git-sync.py 新增 push 重试机制（3次重试，间隔3秒），防止网络抖动导致同步丢失 |
| v1.3.0 | 2026-08-10 | **双机互联优化**：球队画像(球队画像档案库)纳入 EXTRA_SYNC 自动同步；git-sync.py 支持绝对路径映射；pull 后写入时间戳(.last_pull_time)支持时效检查；push 后自动提醒另一端 pull |
