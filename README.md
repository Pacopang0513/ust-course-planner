# UST 自动选课助手

面向香港科技大学学生的**实验性选课与课表规划助手**。项目把公开课表、个人
SIS 信息、培养方案与 USTSpace 课程评价汇总到一个带检查点的工作流中，帮助学生
整理候选课程、检查先修条件与时间冲突，并生成多套课表方案。

> [!IMPORTANT]
> 本项目仍在测试阶段，**不能替代 SIS Academic Requirements（AR）、学院或
> Academic Registry 的正式毕业审核**，也不会代替用户在 SIS 中提交选课。
> 任何毕业学分、专业要求、waiver 或选课资格结论，都应以学校官方系统与书面确认
> 为准。

## 项目状态

| 能力 | 当前状态 | 说明 |
|---|---|---|
| 公开 WCQ 课表抓取 | 可用 | 获取开课、section、教师、时间与先修要求 |
| 课程时间冲突检查 | 可用 | 生成无直接时间冲突的候选课表 |
| USTSpace 评价整理 | 可用，但依赖登录权限 | 社群数据仅作为参考，不是官方结论 |
| 主修与扩展主修要求整理 | 实验性 | 必须与 SIS AR 逐项核对 |
| 副修要求合并 | 尚未完整支持 | 副修信息可被识别，但目前不会可靠地合并进排课结果 |
| 剩余学分与毕业学期估算 | 已知不可靠 | 选修池 quota、部分完成及跨栏位重复课程可能导致明显高估 |
| 自动提交选课 | 不支持 | 项目只生成建议，不操作 SIS 选课 |

当前实现适合用作“整理信息与比较方案”的辅助工具，不适合单独用于判断能否毕业。

## 能做什么

- 从 WCQ 获取目标学期的课程、section、教师、时间及先修要求；
- 读取 SIS 中的课程历史、Academic Requirements 与学校预选课；
- 将候选课程按必修、专业选修及 Common Core 等栏位整理；
- 参考 USTSpace 的课程与教师评价，对候选课程进行排序；
- 按目标学分、上课天数及用餐时段等偏好生成多套无直接时间冲突的课表；
- 输出课程权衡说明、周历视图与选课时间提醒。

## 开始之前

### 1. 准备运行环境

项目需要能读取仓库并运行本地命令的 AI 编程助手。当前工作流主要按 OpenCode
设计，也可以使用具备等价能力的其他工具。模型或平台的免费额度可能随时变化，
本项目不保证任何特定模型长期免费。

Python 最低版本为 **3.10**，推荐使用 **Python 3.12**：

```bash
git clone https://github.com/Pacopang0513/ust-course-planner.git
cd ust-course-planner

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. 准备 USTSpace 权限

[USTSpace](https://ust.space/home) 是非官方课程评价社区。若要读取完整评论，请先在
网站登录并确认自己的账户已有相应权限。USTSpace 的评分、评论与工作量信息只代表
社区反馈。

### 3. 在本地配置登录 Cookie

完整流程需要两个网站的现有登录会话：

| 名称 | 来源 | 用途 |
|---|---|---|
| `PS_TOKEN` | HKUST SIS | 读取课程历史、AR 与预选课 |
| `ustspace_session` | USTSpace | 读取课程评分与评论 |

它们是浏览器登录 Cookie，**不是 AI API key**。AI 模型服务不会自动取得学校或
USTSpace 的登录权限。

> [!CAUTION]
> Cookie 等同于临时登录凭据。不要把 Cookie 粘贴到 AI 对话、GitHub Issue、PR、
> 截图或日志中，也不要提交 `credentials/cookies.txt`。

先在浏览器中登录 SIS（包括 MFA）与 USTSpace，然后只在自己的终端运行：

```bash
python scripts/cookies_setup.py
python scripts/cookies_setup.py --check
python scripts/ustplan.py doctor
```

交互脚本会在本地接收 Cookie，并把它们保存到 Git 忽略的
`credentials/cookies.txt`。预检只应显示 `OK`、`EXPIRED`、`MISSING` 或
`UNREACHABLE`，不会显示 Cookie 值。

在 macOS/Linux 上，建议额外限制凭据文件权限：

```bash
chmod 600 credentials/cookies.txt
```

Cookie 失效后请重新运行配置脚本。停止使用项目时，可以删除
`credentials/cookies.txt`，并在相关网站退出登录以结束会话。

## 使用流程

1. 在 AI 编程助手中打开本项目；
2. 在本地终端完成 Cookie 配置与 `doctor` 预检；
3. 对助手说“帮我排下学期的课”，并提供主修、扩展主修、副修、track 与目标学期；
4. 将系统整理出的未修清单与 SIS AR 逐项核对；
5. 确认目标学分与需要排除或申请 waiver 的课程；
6. 比较生成的课表方案，最后由本人到 SIS 完成选课。

工作流概览：

```text
读取 SIS 与培养方案
        ↓
整理候选课程栏位
        ↓
核对目标学期开课与先修要求
        ↓
整理 USTSpace 社群评价
        ↓
评分、过滤与课表编排
        ↓
输出多套方案与报告
        ↓
用户核对并自行在 SIS 选课
```

## 已知限制

- **剩余学分可能严重高估**：当前实现可能把选修池中的全部候选课程学分相加，
  而不是只计算满足 quota 所需的课程；部分完成的栏位及跨栏位重复课程也可能重复
  计入。不要依据该数值制定毕业计划。
- **副修尚未完整纳入排课**：副修信息会被读取，但当前逻辑不会可靠地把副修要求
  合并进未修清单与课表。请单独对照副修课程表及 SIS AR。
- **特殊规则无法穷尽**：双主修 double count、course substitution、waiver、
  credit transfer、Honors 等价及培养方案年份差异，都需要官方确认。
- **评价存在样本偏差**：USTSpace 热度与评分不是教学质量的官方衡量，少量评论不应
  被视为稳定结论。
- **登录会话会过期**：`PS_TOKEN` 与 `ustspace_session` 需要定期在本地更新；
  项目不会绕过 MFA，也不应保存学校密码或 Duo 验证码。

如果结果与 SIS AR 不一致，请停止使用有冲突的结论，并以 SIS AR、学院 adviser 或
Academic Registry 的回复为准。

## 隐私与安全

- 只授予项目完成规划所需的最小数据访问范围；
- 凭据与运行时个人数据应只保存在本机，不要提交到 Git；
- 分享日志、报告或截图前，先检查姓名、学号、成绩、Cookie 与课程历史；
- 项目不会自动注册课程，也不应自动批准 Duo/MFA 请求；
- 若凭据意外泄露，请立即退出相关网站会话并重新登录，使旧会话失效。

## 开发与验证

开发者命令、目录结构、schema 与排障流程请参阅：

- [开发者文档](docs/DEVELOPER.md)
- [架构设计](docs/ARCHITECTURE.md)
- [排障手册](docs/RUNBOOK.md)
- [变更记录](CHANGELOG.md)

提交功能改动时，除单元测试外，还应使用能覆盖真实组合规则的端到端 fixture。单元
测试通过并不代表主修、扩展主修、副修、quota 与 double-count 的组合结论正确。

## 反馈与贡献

欢迎提交可复现的 Issue 或 PR。请提供脱敏后的输入结构、预期结果、实际结果与运行
环境，**不要附带 Cookie、学号、成绩单或未经脱敏的 SIS 页面**。
