# UST 自动选课助手
- The AI course-planning assistant for UST students；
- 基于Opencode harness与Deepseek V4 Flash(0731)开发的Agent；
- 仍在测试阶段，结果仅供参考。（因为过程中可能会有很多很多奇怪的BUG是有限样本测不出来的）；

---

## 简介
- 考虑到同学们天天问什么CC好，以及为了节省对照USTspace评论、编排时间表的时间，所以写了用户友好优先的"简易Agent"；
- 这是一个面向香港科技大学学生的选课辅助工具。它由Claude Code、opencode等AI编程助手平台运行；
- 同时也是两位作者第一次尝试Agent harness，技术与流程并不成熟，若有优化建议还请提出；
- 能做到的事情：
  - 半自动化：只需要手动输入两个cookie、以及你希望选择的track，便能自动进行分析，无需编程基础；
  - 算清还差什么课：通过SIS系统对照你的专业毕业要求，逐项列出还没修的课程；
  - 看口碑再选课：参考ustspace中学生们对每门课的真实评价（给分、教学、内容、工作量），排出综合最优的课程；
  - 排出不冲突的课表：自动生成多套无时间冲突的课程表方案，供你挑选；

---

## 使用说明

### 开始之前

### Opencode
- **Opencode 是什么**：一个开源的 AI 编程助手，通过对话的方式，自行读写文件、执行脚本、运行项目；
- **为什么选择 Opencode**：
  - **免费**：内置免费的DeepSeek V4 Flash(0731)模型，不用花钱；
  - **易用**：UI界面简单，无需配置环境；

### USTSpace
- **USTSpace是什么**：一个非官方的社群，能在上面看到所有UST课程的评论及评分；
- **USTSpace怎么使用**：
  - 登录网站https://ust.space/home ；
  - 获取阅读全部评论的权限，需要你至少评论一次后解锁；
  - 此Agent需要通过分析USTSpace的评论以对课程进行排序，因此请确认已获取此权限；

### 事前输入
- 0. **部署模型**:
  - 【若你自己拥有api，可选择任意一个AI编程助手及任意一个模型作为代替，以下使用Opencode ＋ Deepseek V4 flash作免费使用参考】
  - 在官网https://opencode.ai/zh/download下载Opencode桌面版；
  - 将本文件下载到电脑上，由Opencode选取文件夹后即可使用；
  - 记得手动选择内置的Deepseek V4 flash模型；
- 1. **获取登录令牌**：
  - 在浏览器分别登录SIS教务系统中的Student Center、以及USTSpace；
  - 按键盘F12，打开"开发者工具"；
  - 点击顶部栏的"+"，选择"应用程序"（Application）标签；
  - 左侧栏展开点击"Cookie"；
  - 找到名称为 `PS_TOKEN`（SIS）及 `ustspace_session`（USTSpace）的登录令牌；
  - 双击"值"一列，全选复制（Ctrl+C），粘贴给 AI 即可；
- 2. **专业信息**：
  - 你必须向Agent提供你希望就读的major track；
  - 除此之外，若能提供major/extend major/minor等信息，能提高Agent准确性；

### 使用流程
- **第一步**：打开 opencode 进入本项目，说一句"帮我排下学期的课"；
- **第二步**：提供两个网站的登录令牌，并提供个人专业信息；
- **第三步**：确认未修清单及目标学分，以获取完整分析报告；

> 中途你可以随时要求Agent回答你希望了解的问题；

---

## 工作流

```
开始
  │
  ▼
① 读取你的信息 ── 从 SIS 拉取专业、已修学分、毕业要求、学校预选课
  │
  ▼
② 计算未修课程 ── 对照专业培养方案，把"还差什么"按必修/选修/通识分栏位列出
  │
  ▼
③ 核对本学期开课 ── 对照本学年课程表：没开的课移除，先修课没满足的进行标记
  │
  ▼
④ 查课程口碑 ── 从 USTspace 拉取评分、热度、任课教授口碑
  │
  ▼
⑤ 量化打分排序 ── 四维评分及额外权重，每类课程排出优先级
  │
  ▼
⑥ 编排课表方案 ── 生成多套无时间冲突的方案（学分、课程组合各有侧重）
  │
  ▼
⑦ 输出报告 ── 完整报告 + 周历 + 选课时间提醒 + 导入Timetable plannar
```



## 附录：开发者与深入阅读

- 命令行版说明（快速开始 / 命令表 / 目录结构）：[`docs/DEVELOPER.md`](docs/DEVELOPER.md)
- 架构设计：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 排障手册：[`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- 变更记录：[`CHANGELOG.md`](CHANGELOG.md)
