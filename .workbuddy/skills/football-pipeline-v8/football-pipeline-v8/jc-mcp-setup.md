# jc-mcp 安装指引

## 一台机器安装即可，GitHub 同步配置到另一台

### 第一台（已装好）
- 路径: `C:/Users/xieyu/.workbuddy/mcp-servers/jc-mcp/`
- MCP 配置: `C:/Users/xieyu/.workbuddy/.mcp.json`
- 正常使用即可

### 第二台（新机器）
```bash
# 1. 确保 Node.js >= 18 已安装
node --version

# 2. 克隆 jc-mcp
mkdir -p ~/.workbuddy/mcp-servers
cd ~/.workbuddy/mcp-servers
git clone https://github.com/li3jia4hao5-hue/jc-mcp.git
cd jc-mcp
npm install
npm run build

# 3. MCP 配置已通过 git-sync push/pull 同步到 ~/.workbuddy/.mcp.json
#    无需手动修改，football-sync pull 自动拉取

# 4. 重启 CodeBuddy 即可使用
```

### 验证
在 CodeBuddy 对话中输入：
```
用 jc-mcp 看一下今天竞彩有什么比赛
```

如果返回比赛列表 + 赔率，说明安装成功。

### MCP 配置文件位置
`.mcp.json` 已加入 git-sync 的 EXTRA_SYNC 列表。
每次 sync pull/push 会自动同步两台电脑的 MCP 配置。

### jc-mcp 提供的工具
| 工具 | 用途 |
|------|------|
| `get_jc_odds` | 全5种玩法赔率（SPF/让球/比分/总进球/半全场） |
| `get_jc_odds_simple` | 快速赔率速览（胜平负 + 让球） |
| `get_jc_match_odds` | 特定对阵的深度分析（隐含概率/返奖率/凯利值） |
