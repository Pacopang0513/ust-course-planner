# SIS 系统结构与数据抓取说明

> 来源：HKUST SIS (PeopleSoft Campus Solutions) 抓取经验整理（2026-08）
> 用途：`scripts/sis/parser.py` 的技术参考
> 说明：PeopleSoft 无公开 API，只能通过 HTML 抓取；本文档记录认证、URL、HTML 结构与已知陷阱。

## 1. 认证体系

### Cookie 清单

| Cookie | 用途 | 必须 | 获取方式 |
|--------|------|:----:|----------|
| `JSESSIONID` | Weblogic/PeopleSoft 会话标识，格式 `<随机字符串>!<数字>` | ✅ | 访问即自动获得 |
| `PS_TOKEN` | PeopleSoft 认证令牌，CAS 登录后签发 | ✅ | CAS SSO 认证后从浏览器复制 |
| `lcsrftoken` | CSRF 防护令牌，GET 请求无需 | ❌ | 登录时自动设置 |
| `PS_TOKENEXPIRE` | Token 过期时间戳 | 自动 | 随请求附带 |
| `PS_LOGINLIST` | 登录列表 URL | 自动 | 随请求附带 |
| `PS_LASTSITE` | 上次访问站点 | 自动 | 随请求附带 |

### 认证流程

```
浏览器访问 SIS → 302 重定向（设置 JSESSIONID）
  → 返回登录页 → JavaScript 检测未认证
  → 重定向到 cas.ust.hk → ITSC 账号登录
  → CAS 重定向回 PeopleSoft → 系统签发 PS_TOKEN
  → 从 DevTools → Application → Cookies 复制 JSESSIONID 和 PS_TOKEN
```

### Cookie 过期

- `PS_TOKEN` 有过期时间（见响应 header 的 `PS_TOKENEXPIRE`）
- 过期后需重新通过浏览器登录获取（脚本需处理此情况）

## 2. 服务器架构

| 组件 | 域名/路径 | 用途 | 数据量 |
|------|----------|------|--------|
| Portal Servlet | `sisprod.psft.ust.hk/psp/` | 页面框架（导航栏、菜单壳） | ~24KB |
| Content Servlet | `sisprod.psft.ust.hk/psc/` | **实际内容页面（含数据）** | 70~230KB |
| Cache | `sisprod.psft.ust.hk/cs/` | 静态资源（JS/CSS/图片） | — |

**关键区别**：`psp` = 壳，`psc` = 数据。抓取数据**必须用 `psc`**。

## 3. 关键 URL 与组件

### 3.1 Student Center（导航中心）

```
GET /psc/SISPROD/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL
```

- 页面标题：`<学生姓名>'s Student Center`
- 包含 "My Academics" 下拉菜单，选项值映射：

| Value | 页面 | Component |
|-------|------|-----------|
| `2050` | Course History | `SSS_MY_CRSEHIST` |
| `3010` | Academic Requirements | `SAA_SS_DPR_ADB` |
| `1002` | Class Schedule | — |
| `1030` | Grades | `SSS_TERM_GRADE` |
| `2035` | Transcript: View Unofficial | `SSS_TSRQST_VIEW` |
| `1005` | Enrollment: Add | — |
| `1020` | Exam Schedule | — |
| `2025` | Transfer Credit: Report | — |
| `3020` | What-if Report | — |

### 3.2 Course History（课程历史）

```
GET /psc/SISPROD/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.SSS_MY_CRSEHIST.GBL?Page=SSS_MY_CRSEHIST&Action=U
```

- 页面标题：`My Course History`
- 网格字段（`$N` = 行索引，从 0 开始）：

| 字段 ID | 内容 |
|---------|------|
| `CRSE_NAME$N` | 课程代码（如 `CHEM 1011`） |
| `CRSE_DESCR$N` | 课程名称（如 `General Chemistry A`） |
| `CRSE_GRADE$N` | 成绩（如 `A+`, `T`, `P`, `EX`） |
| `CRSE_TERM$N` | 学期（如 `2024-25 Fall`） |
| `CRSE_UNITS$N` | 学分（如 `3.000`） |

### 3.3 Academic Requirements（学术要求/毕业进度）

```
GET /psc/SISPROD/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.SAA_SS_DPR_ADB.GBL
```

- 页面标题：`My Academic Requirements`，约 230KB
- 需求组按 `PAGROUPDIVIDER` 分割，每组内含 `Satisfied` / `Not Satisfied` / `In Progress` 状态标签
- 注意：学术要求报告**每年 10 月更新一次**（按 Curriculum Handbook）

## 4. PeopleSoft 导航机制

### 4.1 导航流程

```
Step 1: GET Student Center → 提取 <input id="ICSID" value="...">
Step 2: POST Student Center（表单导航）
    ICType=Panel / ICSID=<Step1 获取> / ICStateNum=3
    ICAction=DERIVED_SSS_SCL_SSS_GO_1
    DERIVED_SSS_SCL_SSS_MORE_ACADEMICS=<目标页面 value>
Step 3: 302 重定向 → GET 目标页面 → 返回含数据的 HTML
```

### 4.2 ICSID

- 每次访问 Student Center 生成新值；格式：`/TzKZed+60Gyaq9qmgS81WlOqMTR7TL0KtZq+yLNTCg=`
- 提取正则：`ICSID' id='ICSID' value='([^']*)'`
- **POST 导航必须携带，否则 403**
- ICSID 是一次性的 — 每次导航前都需要重新获取

### 4.3 导航表单参数（固定值）

```
ICType=Panel / ICElementNum=0 / ICStateNum=3 / ICAction=DERIVED_SSS_SCL_SSS_GO_1
ICModelCancel=0 / ICXPos=0 / ICYPos=0 / ResponsetoDiffFrame=-1
TargetFrameName=None / FacetPath=None
外加 ICSID（动态）+ DERIVED_SSS_SCL_SSS_MORE_ACADEMICS（目标页面值）
```

## 5. HTML 数据结构

### 5.1 Course History 页面结构

```html
<!-- 学生姓名 -->
<div id='win0divDERIVED_SSTSNAV_PERSON_NAME'>STUDENT_NAME</div>

<!-- 课程网格（每行一个 $N 索引，N=0,1,2,...） -->
<div id='win0divCRSE_NAME$0'><span id='CRSE_NAME$0'>CHEM 1011</span></div>
<div id='win0divCRSE_GRADE$0'><span id='CRSE_GRADE$0'>A</span></div>
<div id='win0divCRSE_TERM$0'><span id='CRSE_TERM$0'>2024-25 Fall</span></div>
<div id='win0divCRSE_UNITS$0'><span id='CRSE_UNITS$0'>3.000</span></div>

<!-- 课程名称（超链接） -->
<a class='PSHYPERLINK'>General Chemistry A</a>
```

### 5.2 Academic Requirements 页面结构

```html
<!-- 需求分类标题（PAGROUPDIVIDER = 一级分组） -->
<td class='PAGROUPDIVIDER'>Common Core Group - Foundations I</td>
<td class='PAGROUPDIVIDER'>PHYS Required Course (Part 1)</td>

<!-- 需求描述（含状态） -->
<span class='PSLONGEDITBOX'>
  <strong>Not Satisfied: &nbsp;&nbsp;</strong>
  At least 3 credits must be from Arts (A).
</span>

<!-- 可折叠子项 -->
<a id='DERIVED_SAA_DPR_GROUPBOX3$42' aria-expanded='true'>PHYS Course</a>

<!-- 课程代码 -->
<span id='...LABEL'>LIFS1901</span>
```

### 5.2a 需求组内逐课网格（`parse_academic_requirements` 已提取）

每个需求组内有一个课程网格，字段以 `$N` 索引关联：

| 字段 ID | 内容 |
|---|---|
| `CRSE_NAME$span$N` | 课程代码（如 `PHYS1113`，无空格） |
| `CRSE_DESCR$N` | 课程名（如 `Lab Gen Phys I`） |
| `CRSE_UNITS$N` | 学分（如 `1.00`） |
| `CRSE_WHEN$N` | ⚠️ **不可靠**：已修课=修读学期；未修课=开课学期（`Fall, Spring`） |
| `SAA_ACRSE_AVLVW_CRSE_GRADE_OFF$N` | **可靠信号**：已修课=成绩（`B+`）；未修课=`&nbsp;`（空） |

**判定规则**：`grade 非空 → taken；否则 not_taken`。输出到 `requirement_groups[].courses`。
需求组级状态（`satisfied/not_satisfied/in_progress`）由 SIS 系统按 Curriculum Handbook 判定（每年 10 月更新），**直接信任**，不要用 curriculum PDF 重算。

### 5.3 Grade 含义

| Grade | 含义 | Grade | 含义 |
|-------|------|-------|------|
| A+, A, A- | 标准字母成绩 | B+, B, B- | 标准字母成绩 |
| C+, C, C- | 标准字母成绩 | P, PP | Pass |
| F | Fail | T | Transfer Credit（转学分） |
| AU | Audit（旁听） | EX | Exempted（豁免） |
| I | Incomplete | | |

### 5.4 Term 格式

```
2023-24 Fall    2023-24 Spring    2023-24 Summer
2024-25 Fall    2024-25 Spring    2024-25 Summer
2025-26 Fall    ...
```

## 6. 工具脚本（本项目）

| 脚本 | 功能 | 输出 |
|---|---|---|
| `scripts/sis/parser.py` | 统一工具：`--fetch` 抓取 + 本地 HTML 解析 | `cache/sis/` 下 JSON + 原始 HTML |

cookie 文件位置：`credentials/cookies.txt`（用户手动创建，AI 禁读），格式：

```
JSESSIONID=xxx!1442537993
PS_TOKEN=<your-token-value>
```

### 输出 JSON 结构

**sis_course_history.json：**

```json
{
  "student": { "name_full": "<学生姓名>", "name_en": "", "name_zh": "" },
  "summary": {
    "total_courses": 42,
    "taken": 39,
    "in_progress": 0,
    "transferred": 1,
    "total_units": 107.0
  },
  "courses": [
    {
      "index": 0,
      "code": "CHEM 1011",
      "description": "General Chemistry A",
      "grade": "A",
      "term": "2024-25 Fall",
      "units": 3.0,
      "status": "taken"
    }
  ]
}
```

**sis_academic_req.json：**

```json
{
  "student": { "name_full": "<学生姓名>" },
  "requirement_groups": [
    {
      "name": "Common Core Group - Foundations I",
      "status": "not_satisfied",
      "satisfied_count": 0,
      "not_satisfied_count": 2,
      "in_progress_count": 0,
      "related_courses": []
    }
  ],
  "requirement_items": [
    {
      "status": "not_satisfied",
      "description": "At least 3 credits must be from Arts (A)."
    }
  ]
}
```

## 7. 数据抓取方法总结

### 方法 A：直接 `psc` URL + Cookie（已知 URL 时使用）

```bash
curl -s -H "Cookie: JSESSIONID=...; PS_TOKEN=..." \
  "https://sisprod.psft.ust.hk/psc/SISPROD/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.SSS_MY_CRSEHIST.GBL?Page=SSS_MY_CRSEHIST&Action=U"
```

### 方法 B：POST 导航（通过下拉菜单跳转）

```bash
# 1. 获取 ICSID
ICSID=$(curl -s -H "Cookie: ..." \
  "https://sisprod.psft.ust.hk/psc/SISPROD/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL" | \
  grep -oP "ICSID' id='ICSID' value='[^']*'" | cut -d"'" -f2)

# 2. POST 导航 + 跟随重定向
curl -s -L -H "Cookie: ..." \
  --data-urlencode "ICSID=$ICSID" \
  --data-urlencode "ICAction=DERIVED_SSS_SCL_SSS_GO_1" \
  --data-urlencode "DERIVED_SSS_SCL_SSS_MORE_ACADEMICS=2050" \
  ...其他固定参数... \
  "https://sisprod.psft.ust.hk/psc/SISPROD/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL"
```

### 方法 C：Python 脚本（推荐）

```bash
python3 scripts/sis/parser.py --fetch --cookie-file credentials/cookies.txt
```

## 8. 已知问题与陷阱

### 8.1 Section 边界提取

**问题**：`html.find()` 找不到字符串时返回 `-1`，`min()` 会错误选中 `-1`，导致 section 覆盖整个页面。

**修复**：过滤掉 `-1` 值后再取 `min()`。

```python
# ❌ 错误写法
next_pos = min(html.find(d, pos) for d in dividers)

# ✅ 正确写法
candidates = [p for d in dividers if (p := html.find(d, pos)) != -1]
next_pos = min(candidates) if candidates else len(html)
```

### 8.2 HTML 实体

- `PAGROUPDIVIDER` 中的文本可能含 `&amp;`（如 `Foundations II &amp; Experiencing`）
- 用于 `html.find()` 搜索时保留原样（HTML 中就是 `&amp;`）
- 用于显示时调用 `html.unescape()` 解码为 `&`

### 8.3 提取字段值

PeopleSoft 中同一个字段可能有多种渲染模式，需要依次尝试：

```python
patterns = [
    r"id='FIELD_ID'\s*>\s*<span[^>]*>([^<]*)</span>",  # 最常见
    r"id='FIELD_ID'\s*>\s*([^<]*)<",                     # 直接文本
    r"id='FIELD_ID'[^>]*value='([^']*)'",                # input 标签
]
```

### 8.4 Cookie 过期

- `PS_TOKENEXPIRE` 指示过期时间
- 过期后 `POST` 导航会失败（不重定向到目标页）
- 症状：页面返回 "You are not authorized" 或一直停留在 Student Center

## 9. 可基于抓取数据实现的功能

- 毕业进度跟踪 — 对比 course history vs academic requirements
- GPA 计算 — 按学期/按科目统计
- 排课推荐 — 根据 requirements 缺口推荐下学期的课
- What-If 分析 — 模拟换专业后的学分转移
- 课程表冲突检测 — 结合 Class Schedule 数据
- 学位审计 — 自动判断是否可以毕业

## 10. 注意事项

1. Cookie 会过期，需定期手动更新
2. PeopleSoft 无公开 API，只能 HTML 抓取
3. 学术要求报告每年 10 月更新一次（根据 Curriculum Handbook）
4. 抓取结果仅供参考，正式毕业要求以学术顾问为准
5. PeopleSoft 页面 ID 格式可能因 PeopleTools 版本升级而变化
6. `psp` 和 `psc` 返回的内容完全不同，抓取数据必须用 `psc`
7. ICSID 是一次性的 — 每次导航前都需要重新获取
