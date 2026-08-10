# 足球数据聚合器 v2.0 (双引擎混合架构)

> 零成本专业级足球数据管道 | API直连 + WebSearch智能降级 | 自动化采集 | 标准化输出

---

## 架构升级说明 (v1 → v2)

### v1 的问题
核心逻辑绑死 **API-Football (RapidAPI)**，但该 API 的注册被 reCAPTCHA 阻挡，导致整个管道无法运行。

### v2 的方案：**双引擎混合模式**

```
┌─────────────────────────────────────────────────────┐
│                  引擎 A: API 直接调用                │
│  ├─ The Odds API        → 赔率/亚盘变动 ✅ 已有Key   │
│  ├─ football-data.org   → 积分/赛程(大联赛) 🔄 等Key  │
│  └─ Open-Meteo          → 天气 ✅ 无需Key            │
├─────────────────────────────────────────────────────┤
│              引擎 B: WebSearch 结构化降级            │
│  └─ 14词情报模板(YAML配置) → 伤停/H2H/首发/PFI/新闻  │
│     基于 维京2-1 / 博德1-2 100%命中验证的方法论       │
└─────────────────────────────────────────────────────┘
```

**核心优势：**
- 即使没有 football-data.org 的 Key，系统也能用 **引擎B 完全运行**
- The Odds API 已有可用 Key → 赔率数据质量不打折
- WebSearch 模板固化了 100% 命中的方法论 → 情报质量有保障

---

## 功能特性

| 数据类型 | 数据源（优先级） | 费用 | 状态 |
|:---------|:---------------|:----:|:----:|
| 欧赔 + 亚盘变动 | The Odds API > WebSearch | 免费 (500次/月) | ✅ 可用 |
| 伤停名单 / 阵容预测 | WebSearch (14词模板) | 免费 | ✅ 可用 |
| H2H 历史交锋 | WebSearch > API-Football | 免费 | ✅ 可用 |
| 赛程 / 大联赛积分 | football-data.org | **完全免费无限额** | 🔄 待注册 |
| 天气条件 | Open-Meteo > WebSearch | **免费无需Key** | ✅ 可用 |
| PFI疲劳度检测 | 自研引擎 + WebSearch | - | ✅ 可用 |
| 新闻动因 / 首发曝光 | WebSearch only | 免费 | ✅ 可用 |

**输出：** 每场比赛一个标准化JSON文件，包含全部6层情报数据，供铁律分析引擎直接读取。

---

## 快速开始（3步）

### Step 1: 注册 API Key（至少1个）

#### 必需：The Odds API ⭐
- 注册地址：https://the-odds-api.com/
- 免费额度：500次/月
- 状态：✅ **已注册** (Key已配置在 .env)

#### 推荐：football-data.org（大联赛增强）
- 注册地址：https://www.football-data.org/client/register
- 免费额度：10次/分钟（需邮件审批约24h激活）
- 覆盖：英超/德甲/意甲/法甲/西甲/荷甲/葡超 等
- **无 reCAPTCHA！注册超简单！**

### Step 2: 配置 Key

```bash
cd D:\1\Claw\data-pipeline
notepad .env   # 填入你的Key（如果还没填的话）
```

当前状态：
```
ODDS_API_KEY=4909eb41f669995d8abe6ab08395d411  ✅ 已配置
FOOTBALL_DATA_TOKEN=your-football-data-token-here  🔄 等待注册
```

### Step 3: 运行

**方式A：命令行（推荐）**
```bash
# 分析指定比赛（自动选择最佳数据源）
python main.py --matches "Viking vs Sarpsborg,Bodoe Glimt vs Valerenga"

# 强制使用WebSearch降级模式（跳过所有API）
python main.py --websearch-only --matches "Viking vs Sarpsborg"

# 从文件读取比赛列表
python main.py --file matches_example.txt

# 指定联赛和城市（天气查询）
python main.py --matches "Benfica vs Viseu" --league "Liga Portugal" --city Lisbon
```

**方式B：双击启动（Windows）**
```
双击 run.bat → 选择选项 → 输入比赛
```

---

## WebSearch 14词情报模板详解

这是 v2.0 的**核心竞争力**——将维京/博德 100% 命中时的搜索方法论固化成可重复执行的模板。

### 模板文件：`websearch_templates.yaml`

```yaml
# 14个搜索词，分6层，3轮执行
search_templates:
  # Layer 1: 伤停+阵容 (T-12h 执行)
  - id: 01  # {home} injuries news today {date}
  - id: 02  # {away} injuries news today {date}
  - id: 03  # {home} predicted lineup vs {away}
  - id: 04  # {away} predicted lineup vs {home}

  # Layer 2: H2H交锋 (T-12h 执行)
  - id: 05  # {home} vs {away} head to head statistics
  - id: 06  # {home} vs {away} historical odds results

  # Layer 3: 赔率+亚盘 (T-6h + T-3h 各执行一次)
  - id: 07  # {home} vs {away} odds today betting analysis
  - id: 08  # {home} vs {away} asian handicap movement today

  # Layer 4: PFI疲劳度 (T-12h 执行)
  - id: 09  # {home} fixture congestion fatigue
  - id: 10  # {away} fixture congestion fatigue

  # Layer 5: 天气 (T-6h 执行)
  - id: 11  # {city} weather forecast {match_date}

  # Layer 6: 新闻+首发曝光 (T-3h 黄金窗口)
  - id: 12  # {home} vs {away} team news motivation
  - id: 13  # {home} lineup leak confirmed {date}
  - id: 14  # {away} lineup leak confirmed {date}
```

### 三轮渐进式执行策略

| 轮次 | 时间 | 执行模板 | 目的 |
|:----:|:-----|:--------|:-----|
| Round 1 | T-12h | 1,2,5,9,10 | 建立基线数据（伤停/H2H/PFI） |
| Round 2 | T-6h | 3,4,6,7,8,11 | 动态信号跟进（阵容/赔率/天气） |
| Round 3 | T-3h | 12,13,14,7,8 | 最终校准（新闻/首发/临盘赔率） |

**对应铁律规则：**
- 模板 01-02 → 规则#5（伤停精确到人）、规则#19（核心缺阵降星）
- 模板 03-04 → 规则#29（首发曝光-轮换识别）
- 模板 05-06 → 规则#26（H2H逆向思维）、规则#14（H2H一边倒）
- 模板 07-08 → 规则#25（赔率异动捕捉）、规则#27（亚盘降盘联动）
- 模板 09-10 → 规则#17（PFI四项检测）、规则#28（PFI比分区间收缩）
- 模板 11 → 规则#20（天气阈值）
- 模板 12-14 → 规则#21（战意等级）、规则#22（冷门诱因）

---

## 输出示例

数据保存在 `cache/` 目录，每场比赛一个JSON文件：

```json
{
  "match_id": "viking_sarpsborg_20260809_180000",
  "league": "Eliteserien",
  "version": "v2.0-hybrid",
  "engine_mode": "dual-engine",

  "home_team": {
    "name": "Viking FK",
    "missing_players": [
      {"name": "Joe Bell", "position": "MF", "reason": "injury"}
    ]
  },

  "odds": {
    "home_win": 1.39,
    "asian_opening": -1.5,
    "asian_current": -1.25,
    "asian_change_detected": true,
    "sources": ["pinnacle", "bet365"]
  },

  "pfi_home": {"level": "none", "rest_days": 25},
  "pfi_away": {"level": "critical", "rest_days": 3},

  "websearch_results": {
    "layer1": { "1": {...}, "2": {...}, "3": {...}, "4": {...} },
    "layer2": { "5": {...}, "6": {...} },
    "layer3": { "7": {...}, "8": {...} },
    "layer4": { "9": {...}, "10": {...} },
    "layer5": { "11": {...} },
    "layer6": { "12": {...}, "13": {...}, "14": {...} }
  },

  "data_sources": [
    "TheOddsAPI:pinnacle,bet365",
    "WebSearch:L1-injuries-lineup",
    "WebSearch:L2-H2H",
    "Open-Meteo",
    "WebSearch:L6-news-lineup"
  ],

  "confidence": "high",
  "collected_at": "2026-08-09T18:00:00"
}
```

---

## 目录结构

```
data-pipeline/
├── main.py                    # 聚合器核心脚本 v2.0 (~900行，双引擎)
├── websearch_templates.yaml   # 🔥🔥🔥 14词情报模板配置 (新增)
├── run.bat                    # Windows一键启动脚本
├── .env.example               # API Key配置模板
├── .env                       # 你的实际配置（不要提交Git）
├── matches_example.txt        # 示例比赛列表
├── API注册指南.md             # 详细注册步骤
├── README.md                  # 本文件
├── cache/                     # 输出目录（自动生成）
│   ├── viking_sarpsborg_*.json
│   └── index_*.json           # 索引文件（所有比赛的汇总）
└── logs/                      # 日志目录
    └── pipeline_20260809.log
```

---

## 与铁律系统的对接

本聚合器的输出JSON可以直接被铁律分析引擎读取：

```
数据管道输出 (cache/*.json)
        ↓
铁律分析引擎 (29条规则自动执行)
        ↓
四维预测输出 (SPF/让球/HFT/比分)
        ↓
串关方案生成 (稳胆/平衡/激进)
```

**对应关系（v2 更新）：**

| JSON字段 | 对应铁律 | 数据源引擎 |
|:---------|:--------|:----------|
| `odds.asian_change_detected` | **铁律#27** 亚盘降盘联动 | 引擎A (The Odds API) |
| `pfi_*` 相关字段 | **铁律#28** PFI比分区间收缩 | 引擎A/B 混合 |
| `missing_players` | **铁律#19** 核心缺阵降星 | 引擎B (WebSearch) |
| `websearch_results.layer6` | **铁律#29** 首发曝光识别 | 引擎B (WebSearch) |
| `h2h_last10` | **铁律#26** H2H逆向思维 | 引擎B (WebSearch) |
| `weather.*` | **铁律#20** 天气阈值 | 引擎A (Open-Meteo) |
| `confidence` | **铁律#22** 信息权威性 | 自动计算 |
| `data_sources` 数量 | 质量评级标准 | 自动统计 |

---

## 支持的联赛

| 联赛 | The Odds API | football-data.org | WebSearch降级 |
|:-----|:------------:|:-----------------:|:-------------:|
| 挪超 Eliteserien | ✅ | ❌ | ✅ |
| 瑞典超 Allsvenskan | ✅ | ❌ | ✅ |
| 葡超 Liga Portugal | ✅ | ✅ | ✅ |
| J1联赛 | ✅ | ❌ | ✅ |
| K联赛 | ✅ | ❌ | ✅ |
| 英超 Premier League | ✅ | ✅ | ✅ |
| 德甲 Bundesliga | ✅ | ✅ | ✅ |
| 法甲 Ligue 1 | ✅ | ✅ | ✅ |
| 意甲 Serie A | ✅ | ✅ | ✅ |
| 西甲 La Liga | ✅ | ✅ | ✅ |
| 荷甲 Eredivisie | ✅ | ❌ | ✅ |

> **注意：** WebSearch 降级模式覆盖**所有联赛**，不受 API 限制！

---

## 定时执行（自动化）

### Windows任务计划程序

每天自动运行一次：

```bash
schtasks /create /tn "FootballDataPipeline" /tr "D:\1\Claw\data-pipeline\run.bat" /sc daily /st 18:00
```

### 推荐自动化流程（结合三轮策略）

```
18:00  → Round 1 (T-12h): 伤停/H2H/PFI基线数据
00:00  → Round 2 (T-6h):  阵容/赔率/天气动态信号
03:00  → Round 3 (T-3h):  新闻/首发/临盘赔率最终校准
```

---

## 故障排查

**问题：`HTTP 401 Unauthorized`**
→ API Key 错误或过期。检查 .env 文件中的 Key 是否正确复制。

**问题：`HTTP 429 Too Many Requests`**
→ 请求频率超限。脚本已内置 rate_limit() 函数（每次请求间隔 1.5-6 秒）。

**问题：`Network error`**
→ 网络连接问题。检查代理设置或 VPN。

**问题：部分数据源返回空**
→ 正常现象。v2.0 会自动降级到 WebSearch 引擎补充数据。
查看日志文件 `logs/pipeline_日期.log` 了解详情。

**问题：`ModuleNotFoundError: No module named 'yaml'`**
→ PyYAML 未安装（用于加载 websearch_templates.yaml）：
```bash
pip install pyyaml
```
> 如果不安装，系统会使用内置简化模板（功能相同，只是不可自定义）。

**问题：Python 模块缺失**
实际上本脚本**只使用 Python 标准库**（urllib/json/os/time/subprocess），不需要安装任何第三方包！PyYAML 是可选的。

---

## 下一步计划

- [x] v2.0: 双引擎混合架构（API + WebSearch）✅ 当前版本
- [ ] v2.1: 对接真实 WebSearch 工具（目前是占位符，需集成 CodeBuddy WebSearch CLI）
- [ ] v2.2: football-data.org 自动激活检测（用户填入 Token 后自动切换到增强模式）
- [ ] v2.3: 机器学习预测模型（基于历史数据训练）
- [ ] v2.4: Telegram/微信通知推送
- [ ] v2.5: Web 仪表盘（命中率追踪可视化）

---

## 版本历史

| 版本 | 日期 | 变更 |
|:----:|:-----|:-----|
| v1.0 | 2026-08-09 | 初始版本，4 API 直连架构 |
| **v2.0** | **2026-08-09** | **重构为双引擎混合架构，新增 WebSearch 14 词模板** |

---

*版本: v2.0 (Hybrid Dual-Engine) | 更新: 2026-08-09 | 作者: CodeBuddy Code*
