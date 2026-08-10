# 免费数据API注册指南

> 目标：零成本搭建专业级足球数据管道  
> 预计耗时：30分钟注册全部API + 拿到Key

---

## 一、The Odds API（赔率数据）⭐⭐⭐⭐⭐ 最重要

### 能拿到什么

- 50+家博彩公司实时赔率（bet365/Pinnacle/威廉希尔/立博等）
- **亚盘初盘vs临盘变动历史**（捕获降盘信号的核心！）
- 总进球大小球赔率
- 赛程安排

### 免费额度

- **500次请求/月**
- 够用：每轮分析~25场比赛 × 每场1次请求 = 25次/轮
- 每周2轮 = 50次/月，额度绰绰有余

### 注册步骤

**Step 1：打开官网**

```
https://the-odds-api.com/
```

**Step 2：注册账号**

- 点击右上角 **"Sign Up"**
- 填写邮箱 + 密码
- 验证邮箱

**Step 3：获取 API Key**

- 登录后点击 **"API Keys"** 或 **"My Account"**
- 点击 **"Generate New Key"**
- 复制生成的 Key（格式类似 `xxx-xxx-xxx-xxx`）

**Step 4：确认订阅计划**

- 免费版选择 **"Free"** 计划（500次/月）
- 无需绑定信用卡

### 测试是否成功（浏览器直接访问）

```
https://api.the-odds-api.com/v4/sports?apiKey=你的KEY
```

返回JSON列表 = 注册成功 ✅

---

## 二、API-Football（阵容伤停/H2H）⭐⭐⭐⭐

### 能拿到什么

- **结构化伤停名单**（球员名+位置+原因+缺阵天数+预计回归日期）
- **H2H历史交锋**（近10场直接出JSON）
- 联赛积分榜/射手榜/助攻榜
- 赛事时间表
- **首发阵容预测**（部分联赛支持）

### 免费额度

- **100次请求/天**（RapidAPI免费层）
- 够用：每天分析一次 = ~10-15次请求

### 注册步骤

**Step 1：打开RapidAPI平台**

```
https://rapidapi.com/api-sports/api/api-football/pricing
```

**Step 2：注册RapidAPI账号**

- 点击 **"Subscribe"** → **"Sign Up"**
- 可用Google/GitHub账号快速注册
- 验证邮箱

**Step 3：订阅API-Football**

- 选择 **"Free"** 计划（100次/天）
- 点击 **"Subscribe to Free Plan"**

**Step 4：获取 API Key**

- 进入 **"Endpoints"** 标签页
- 任意一个Endpoint右侧有 **"Code Snippets"**
- 里面包含你的 **X-RapidAPI-Key**（就是API Key）

### 测试（curl命令）

```bash
curl -X GET "https://api-football-v1.p.rapidapi.com/v3/teams?id=529&season=2026" \
  -H "X-RapidAPI-Key: 你的KEY" \
  -H "X-RapidAPI-Host: api-football-v1.p.rapidapi.com"
```

返回球队信息JSON = 成功 ✅

---

## 三、Football-data.org（积分赛程）⭐⭐⭐⭐⭐ 完全免费无限额

### 能拿到什么

- 欧洲主要联赛**实时积分榜**
- 历史比赛结果（DMI/DOIT计算基础）
- 未来赛程安排（PFI疲劳检测输入）
- 球队统计数据

### 免费额度

- **完全免费！无限制！**
- 但需要申请免费Token（审批约24小时）

### 支持的联赛（够用的）

| League Code | 联赛 | 是否覆盖 |
| :---------- | :- | :--- |
| PL          | 英超 | ✅    |
| BL1         | 德甲 | ✅    |
| SA          | 意甲 | ✅    |
| PD          | 西甲 | ✅    |
| FL1         | 法甲 | ✅    |
| PCL         | 葡超 | ✅    |

**⚠️ 不覆盖：挪超/瑞典超/K联赛/J联赛（小联赛需用API-Football补齐）**

### 注册步骤

**Step 1：打开官网**

```
https://www.football-data.org/client/register
```

**Step 2：填写注册表**

- 用户名/密码/邮箱
- 同意使用条款

**Step 3：登录并获取 Token**

- 登录后进入 **"My Data"** 页面
- 复制你的 **Auth Token**

### 测试（浏览器访问）

```
https://api.football-data.org/v4/competitions/PL/standings?season=2026
```

Header中添加：`X-Auth-Token: 你的TOKEN`  
返回英超积分表 = 成功 ✅

---

## 四、Open-Meteo（天气数据）⭐⭐⭐⭐⭐ 完全免费无需Key

### 能拿到什么

- 温度/降水概率/风速/湿度/体感温度
- 逐小时天气预报（未来7天）

### 免费额度

- **完全免费！无需注册！无需API Key！**
- 每分钟10,000次调用（个人用无限）

### 使用方式

直接GET请求，无需认证：

```
https://api.open-meteo.com/v1/forecast?latitude=58.97&longitude=5.73&hourly=temperature_2m,precipitation,windspeed_10m&timezone=Europe/Oslo
```

参数说明：

- latitude/longitude：比赛城市坐标（斯塔万格=58.97, 5.73）
- hourly：需要的天气变量
- timezone：时区

---

## 五、API Key 安全存放

注册完所有Key后，创建配置文件：

**文件路径：** `D:\1\Claw\data-pipeline\.env`（不要提交到Git！）

```env
# ============================================
# 数据管道 API 配置文件
# ⚠️ 不要分享给任何人！包含你的私人API Key
# ============================================

# The Odds API (赔率数据)
ODDS_API_KEY=你的the-odds-api-key-here

# API-Football via RapidAPI (伤停/阵容/H2H)
RAPID_API_KEY=你的rapidapi-key-here
RAPID_API_HOST=api-football-v1.p.rapidapi.com

# Football-data.org (积分/赛程)
FOOTBALL_DATA_TOKEN=你的football-data-token-here

# Open-Meteo (天气) — 无需Key，留空即可
OPEN_METEO_URL=https://api.open-meteo.com/v1/forecast
```



---

## 六、注册完成检查清单

|  # | API                     | 注册状态 | Key获取 | 测试通过 | 备注       |
| -: | :---------------------- | :--: | :---: | :--: | :------- |
|  1 | The Odds API            |   ☐  |   ☐   |   ☐  | 500次/月免费 |
|  2 | API-Football (RapidAPI) |   ☐  |   ☐   |   ☐  | 100次/天免费 |
|  3 | Football-data.org       |   ☐  |   ☐   |   ☐  | 审批需~24h  |
|  4 | Open-Meteo              |   ☐  |  N/A  |   ☐  | 无需Key    |

**全部打勾后 → 运行聚合器脚本 → 开始自动化数据采集**

---

## 七、常见问题

**Q：API Key会过期吗？**

- The Odds API：不会（除非你主动重置）
- RapidAPI Key：90天不使用可能失效（定期调用即可）
- Football-data Token：永久有效

**Q：超出免费额度怎么办？**

- The Odds API：500次/月对个人足够。如果不够可以换免费Key或等到下月重置
- API-Football：100次/天 = 每天1轮分析足够。不要循环调用
- Football-data：无限额

**Q：数据延迟多久？**

- The Odds API：实时（赔率变化秒级更新）
- API-Football：延迟~5-30分钟（取决于联赛）
- Football-data：赛后1-2小时更新结果
- Open-Meteo：每小时更新

**Q：小联赛（挪超/瑞典超/K联/J联）数据哪里来？**

- 赔率：The Odds API 覆盖大部分主流联赛（包括挪超/瑞典超）
- 伤停/阵容：API-Football 覆盖全球900+联赛（包括K联/J联）
- 积分/赛程：Football-data 不覆盖小联赛 → 用 API-Football 的 league standings 接口补齐
- 天气：Open-Meteo 全球覆盖（只要有坐标就行）

---

*下一步：运行 `main.py` 聚合器脚本开始自动采集数据*
