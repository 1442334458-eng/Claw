# 项目长期记忆

## ⚠️ 足球技能存在"双克隆分叉"风险（2026-08-13 发现）

- 同一 GitHub 仓库 `football-betting-analysis` 在本机有两个克隆：
  1. **工作区版**：`D:\1\Claw\.workbuddy\skills\football-betting-analysis`（remote 走 SSH，日常在此工作）
  2. **home 旧版**：`C:\Users\xieyu\.workbuddy\skills\football-betting-analysis.bak`（remote 走 HTTPS，被改名 .bak 但仍在被某些会话写入）
- 2026-08-13 曾出现：14:30 复盘写入 `.bak` 版 history.json（含 `2026-08-09~13` 20 场），工作区版仍停在 8 条。已在当日同步。
- **后续处理 history/lessons 时，先确认改动落在 D:/1/Claw 工作区版**；若发现两版分叉，以内容新者为源合并到工作区版，不要只依赖 git push。

## 足球技能双机同步：路线 A（真 git）约定

- 3 个足球技能目录为独立 git 仓库，支持真正三路合并，不再使用 git-sync.py 的 API 覆盖式推送。
- 本机（xieyu）`github.com:443` 被封锁/抽风，**git 传输统一走 SSH（github.com:22）**。remote 格式：`git@github.com:1442334458-eng/<repo>.git`。
- SSH 密钥：`C:\Users\xieyu\.ssh\id_ed25519_claw`（无口令），已登记到 GitHub 账号 `1442334458-eng`。
- 同步脚本：`D:\1\Claw\.workbuddy\skills\sync_git.bat`，桌面入口 `C:\Users\xieyu\Desktop\GitHub同步.bat`。
- Surface 收敛基准：GitHub `main` HEAD 为 `a68662d`（betting）、`60aed2d`（match）、`e7b5ee8`（pipeline）。

## 分析报告双机同步（2026-08-13 修正，曾误判）

- **关键事实**：老二(Surface) 的 `D:\1\Claw` 跟踪的是 **`football-betting-analysis.git`(main)**，不是 `Claw.git`。本机 `D:\1\Claw` 才是 `Claw.git`(master)。两台机 Claw 目录对应**不同远程仓库**。
- **报告唯一事实来源在本机**：`D:\1\Claw\reports\`（Claw.git, master），但老二不拉这个仓库。
- **让老二看到报告 = 把报告 push 到 `football-betting-analysis.git` 的 `reports/`**：
  - 已验证可用方法：临时克隆 `football-betting-analysis.git` 到 `D:/1/Claw/.fba_tmp`（`git clone -b main --depth 1 git@github.com:1442334458-eng/football-betting-analysis.git .fba_tmp`），cp 报告进 `reports/`，commit 后 `git push origin main`，最后删除 `.fba_tmp`。
  - 也可用 `git-sync.py`（它把本地 reports 经 GitHub API 推到该仓库，但 token 已失效 401，SSH 克隆法更稳）。
  - 已验证：8-13 两份报告推到 `football-betting-analysis.git` main `8418628`，老二 `git pull` 即可见。
- **老二侧操作**：直接 `git pull`（他的 remote 一直是 `football-betting-analysis.git` SSH，无需改动）。
- **曾误判**：先前以为老二跟踪 `Claw.git`、以为 `git-sync.py` 不拉 reports 是根因、并误建了 `sync_claw.bat`（已删除）。实际根因是本机把报告推错了仓库。

## 赔率数据源决策（2026-08-12）

- **弃用 The Odds API**（key 已过期 401，用户明确不再续费/不使用）。pipeline 的 TheOdds 环节视为死源，跑通走 `--no-theodds` 或 WebSearch 兜底。
- 国内平替主力已内置：**500.com**（trade.500.com/jczq，免费无限量，含竞彩官方+49家公司）+ **竞彩官方 API**（webapi.sporttery.cn，中国IP）+ **球迷屋 qiumiwu**（伤停/H2H/数据）。
- The Odds API 价格参考（人民币）：免费500 credits/月；20K credits=$30≈¥216；100K=$59≈¥425。credit≠请求（=markets×regions），历史数据×10。
- 备选付费国产数据源（未接入）：雷速体育商业 API（REST+WS，商务报价）、纳米数据（本次报告用的19家国际赔率）、球探网数据采集。

## 分析报告输出位置（2026-08-12 用户明确要求）

- **最终分析报告一律写到项目根目录 `D:\1\Claw\`**，用 `present_files` 在右侧栏产物里展示。
- 不要写进技能仓库深层目录（如 `.workbuddy/skills/football-pipeline-v8/` 内）——用户觉得难找。
- 命名习惯：日期+场次范围+主题，如 `8-12至8-13_七场完整四猿分析.md`。
- 若报告内容对 skill 有存档价值，可额外在技能目录留副本，但根目录副本必须存在且优先。

## CodeBuddy 自定义模型配置路径（2026-08-13 修正）

- **正确路径**：`%USERPROFILE%\.workbuddy\models.json`（即 `C:\Users\xieyu\.workbuddy\models.json`）
- **错误路径**：`C:\Users\xieyu\.codebuddy\models.json`（此前误建在此，已删除）
- 修改后需**重启 CodeBuddy Code** 才能在下拉菜单看到新模型
- 当前已添加 `glm-5v-turbo`，但能否真正读图取决于：① Coding Plan 是否包含该模型权限；② CodeBuddy 视觉链路是否已启用
- **双机同步**：`models.json` 在 Syncthing `wb-config` 文件夹（`C:/Users/xieyu/.workbuddy`）同步范围内，**自动同步到老二(Surface)**，无需手动复制。老二只需重启 CodeBuddy Code 即可在下拉菜单看到新模型。

## 分析报告标准化输出格式（2026-08-13 用户明确要求）

**每次竞彩分析完成后，必须输出以下两个固定表格：**

### 表 A：四星以上精推表（必输出）
- **触发条件**: 所有信心 ≥ 四星的场次
- **内容列（按此顺序）**:
  1. 优先级（按信心降序 1/2/3...）
  2. 场次号
  3. 联赛
  4. 主队 vs 客队
  5. 信心百分比
  6. SPF 主选（含赔率）
  7. SPF 备选（含赔率）
  8. 让球主选（含赔率）
  9. 让球备选（含赔率）
  10. 比分主选（最可能1个）
  11. 比分备选（次可能2-3个）
  12. 半全场主选
  13. 半全场备选
  14. 核心理由（一句话）
- **文件名格式**: `YYYY-MM-DD_四星以上精推表_防爆冷防平表.md`
- **存放位置**: `D:\1\Claw\reports\` 目录

### 表 B：防爆冷 / 防平警示表（必输出）
- **触发条件**: **不限星级**——只要有爆冷或防平风险就列入
- **内容列（按此顺序）**:
  1. 风险等级（🔴高危 / 🟠中危 / 🟡低危）
  2. 场次号
  3. 联赛
  4. 主队 vs 客队
  5. 赛果倾向（市场主流方向）
  6. 冷门方向（反买方向）
  7. 平局风险（高/中/低）
  8. 触发铁律（哪条规则被触发）
  9. 具体风险描述
  10. 应对策略（建议操作）
- **与表 A 合并同一文件输出**

### 输出时机
- 在全量分析报告（27场完整版）之后立即生成
- 用 `present_files` 展示给用户
- 同时 push 到 GitHub 仓库
