# Career-Loop

> 把「我到底适不适合这个 AI 岗位」从玄学变成 **可证伪、可校准** 的数据闭环。

Career-Loop 是一个面向 **AI / Agent 方向求职者（尤其应届生）** 的开源小工具：它把一份 JD 和你的经历文本喂给一个匹配引擎，给出**预测匹配分 + 缺口清单**；你拿它去投递，再把真实结果（已读 / 面试 / offer）回流，最后用**相关系数**检验「这个匹配分到底准不准」。

准，就继续信它做投递优先级；不准，就说明模型在猜，该反过来用真实数据修权重。

```
   JD（岗位要求）  ──┐
                    ├─►  [匹配引擎] ─►  预测匹配分 + 缺口清单（带原文证据）
   经历（你的简历） ─┘        │
                             │
                     [投递记录] ── 回流真实结果（replied / interview / offer）
                             │
                             ▼
                    [校准模块] ──  r = corr(匹配分, 真实结果)
                             │
                             ▼
              调整能力权重 / 重排投递优先级 / 定位最该补的缺口
```

---

## 为什么做这个

投 AI 产品经理 / Agent 应用岗时，最大的焦虑是：**同一个「我会 Python」「我做过 Agent」在不同 JD 里含金量完全不同**，而你永远在盲投。

市面上的「简历匹配」要么是黑盒打分（你不知道它凭什么给你 80 分），要么只做一次单向匹配就结束，永远不告诉你「上次它说你很匹配，你到底有没有收到面试」。

Career-Loop 的差异化就一句话：**匹配分是可被证伪的**。它能算出一个相关系数 r，直接回答「我这套匹配逻辑，是不是真的在预测结果」。这恰好对应大厂 JD 里反复出现的「建立效果评估体系、用数据验证产品表现」——本项目本身就是这个理念的最小实践。

---

## 它和玩具项目的区别

| 普通简历匹配工具 | Career-Loop |
| --- | --- |
| 黑盒分数，不给依据 | 每项能力附 **JD 原文 + 你的原文证据**，可逐条审计 |
| 一次性打分，打完即忘 | **闭环**：投递 → 回流 → 校准，分数会随真实数据变准 |
| 声称「准确率 95%」 | 自带 **42 条标注评测集** 当回归锁，且明说这是「锁逻辑」不是「真实准确率」 |
| 依赖大模型 API | **零依赖规则基线** 开箱即用，有 OpenAI 兼容 Key 才升级语义匹配，无 Key 自动回退 |

---

## 功能

- **匹配引擎**：JD × 经历 → 14 维能力匹配矩阵（full / partial / missing），每项带原文证据。
- **加权匹配分**：`score = Σ(权重 × 状态分) / Σ权重`，partial 记半分。
- **缺口排序**：按 `权重 × 缺口严重度` 排序，避免高权重硬伤被平均分掩盖。
- **评测集（eval）**：`data/eval_sample.jsonl` 共 42 条（14 能力 × 具备/部分/缺失），`run_eval` 给规则基线打分，作为逻辑回归锁。
- **校准（calibrate）**：Pearson 相关系数 r + 20 分桶正反馈率，判断匹配分是否真能预测结果。
- **本地存储**：SQLite 存候选人 / JD / 投递记录，零外部依赖。
- **看板（可选）**：有 `streamlit` 时一条命令起可视化，无数据时读演示数据。

---

## 安装

需要 Python 3.10+。本仓库**零第三方依赖**即可跑核心逻辑（eval / calibrate / match / 存储）；只有看板需要 `streamlit`。

```bash
git clone https://github.com/<you>/career-loop.git
cd career-loop
pip install -e .            # 装 cli 命令：career-loop
# 可选：看板
pip install streamlit
```

---

## 快速开始

### 1) 生成一份匹配报告（不需要任何 Key）

```bash
career-loop match \
  --jd examples/jd_backend_pm.md \
  --profile examples/profile_me.md \
  --out report.md --json
```

输出示例：

```
匹配度 88.5%  ·  模式 rule  ·  报告已写入 report.md
```

报告里每一项能力都会给：状态图标（🟢🟡🔴）、JD 原文依据、你的原文证据、缺口补法建议。

### 2) 给匹配引擎打分（eval）

```bash
career-loop eval --data data/eval_sample.jsonl --badcases badcases.jsonl
```

```
评测集 42 条　规则基线一致率 1.0
逐能力：python 1.0 / agent 1.0 / rag 1.0 / ... (14 项全 1.0)
无 badcase。
```

> ⚠️ **诚实声明**：一致率 1.0 是在一份**人工构造、刻意覆盖边界case** 的 42 条评测集上取得的，它的作用是**锁住匹配逻辑不被改坏**（回归测试），**不**代表真实世界 100% 准确。真实准确率要靠下面第 4 步的校准和更多真实回流来逼近。

### 3) 校准：匹配分到底准不准（用内置演示数据）

```bash
career-loop calibrate --data data/demo_applications.jsonl
```

```
样本量 29　整体正反馈率 0.448
匹配分 ↔ 真实结果 相关系数 r = 0.694

分桶正反馈率：
    0-20   n=0    率=0.0
   20-40   n=4    率=0.0
   40-60   n=7    率=0.143 ####
   60-80   n=10   率=0.5   ###############
   80-100  n=8    率=0.875 ##########################

结论：中到强相关（|r| ≥ 0.4）。匹配分确实在预测真实结果……
```

> 演示数据是合成的（29 条），用来展示校准模块怎么读、怎么出结论。r=0.694 是**演示数值**，不是真实投递统计。

### 4) 真实闭环：记录投递 → 回流结果 → 校准

```bash
career-loop init                              # 建本地库（默认 ~/.career_loop/loop.db）
career-loop add-profile --name 我 --file examples/profile_me.md
career-loop add-jd      --file examples/jd_backend_pm.md
# 记下打印出的 id，比如 profile=1, jd=1
career-loop apply --jd-id 1 --profile-id 1    # 记录一次投递，自动算预测匹配分
career-loop status                            # 看所有投递
career-loop log --app-id 1 --status interview # 回流真实结果
career-loop calibrate                         # 用真实数据重新校准
```

### 5) 看板（可选）

```bash
career-loop dashboard        # 没有真实数据时读 data/demo_applications.jsonl 演示
```

---

## 能力词表（14 维）

匹配引擎用一张固定的能力词表当无 Key 时的规则基线，也作为所有 JD 的归一化坐标系：

| key | 标签 | key | 标签 |
| --- | --- | --- | --- |
| `python` | Python 工程能力 | `product_sense` | 需求洞察与产品设计 |
| `llm_basics` | 大模型原理与边界 | `data_analysis` | 数据分析与指标体系 |
| `prompt_eng` | 提示词工程 | `eval` | 效果评估体系 |
| `rag` | RAG / 检索增强 | `engineering` | 工程落地与部署 |
| `agent` | Agent / 智能体 | `communication` | 跨团队沟通协作 |
| `function_calling` | 函数调用 / 工具调用 | `domain` | 业务/行业理解 |
| `framework` | Agent 框架使用 | | |
| `coding_tools` | AI 编程工具（Claude Code/Cursor） | | |

每项 JD 要求会被映射到这些 key 上，并带 `weight`（3=核心硬要求 / 2=一般要求 / 1=加分项）和 `kind`（must / nice）。权重决定了缺口排序的优先级。

---

## 目录结构

```
career-loop/
├── career_loop/
│   ├── matching/        # 匹配引擎：schema(词表) / extract / match / llm / render
│   ├── store.py         # SQLite 存储：候选人 / JD / 投递记录
│   ├── calibrate.py     # Pearson 校准 + 分桶 + 结论
│   ├── eval.py          # 标注评测集加载 + 跑分
│   ├── cli.py           # 命令行入口（init/add-profile/add-jd/match/apply/status/log/calibrate/eval/dashboard）
│   └── dashboard.py     # Streamlit 看板（可选依赖）
├── data/
│   ├── eval_sample.jsonl        # 42 条标注评测集（回归锁）
│   └── demo_applications.jsonl  # 29 条合成演示数据（校准演示）
├── examples/            # 示例 JD 与经历
├── gen_eval.py          # 生成评测集的脚本
└── tests/              # 8 个单元测试（匹配 / 校准 / 存储）
```

---

## 设计取舍

1. **规则基线优先，LLM 可选**：没有 API Key 也要能跑、能测、能证伪。LLM 只在可用时作为语义匹配升级，失败自动回退规则。
2. **证据必须逐字摘自原文**：禁止模型「发挥」出证据，保证可审计。这是它和黑盒打分最本质的区别。
3. **评测集当回归锁而非准确率宣称**：42 条全对的意义是「逻辑没被改坏」，不是「真实世界 100% 准」。
4. **相关性而非因果**：校准只回答「匹配分和结果是否单调相关」，不直接说「因为你 score 高所以拿到面试」。
5. **本地优先**：数据存在你自己的 SQLite，不上传任何平台。

---

## 已知局限

- 规则基线靠关键词，遇到高度改写 / 隐喻表达会漏判；这是为什么 LLM 模式和无 Key 回退都要保留。
- 评测集是合成的边界 case，覆盖度有限；真实准确率需要真实回流数据。
- 校准在样本 < 5 时拒绝出结论（避免拿 2 条数据假装显著）。
- 目前只支持中文 JD / 经历（关键词表是中文场景写的）。

---

## 路线图（W1 已完成，W2–W8 进行中）

- ✅ **W1 — 核心闭环**：匹配引擎 + 规则基线 + 评测集锁 + 校准数学（本仓库）。
- 🔜 **W2 — 经历库结构化 + 双向匹配**：不仅 JD→人，还要人→JD（告诉我「我最适合投哪类岗」）。
- 🔜 **W3 — JD 采集**：支持手贴 / 半结构化导入，自动抽岗位要求。
- 🔜 **W4 — 每日投递清单 + 跟踪看板增强**：按校准后的匹配分排优先级，每天该投哪些一目了然。
- 🔜 **W5 — 真实回流 50 条 + 校准上墙**：把校准结果做成 README / 看板里的常驻模块。
- 🔜 **W6 — 50 条人工标注公开评测集**：提升 eval 真实度，这是和同类项目拉开差距的关键。
- 🔜 **W7 — Web 看板 / 分享页**：让非技术同学（面试官）也能一眼看懂。
- 🔜 **W8 — 3 分钟演示视频 + 复盘长文**：用于简历附件和社区传播。

---

## 给招聘方的一句话

如果你在面 AI 产品经理 / Agent 方向，这个项目本身就是我对「用数据验证产品表现」的理解的最小实践：我没有声称我的匹配模型多准，但我给了你一个**能检验它准不准**的方法。

---

## 许可

MIT —— 随便用、随便改、欢迎提 PR。
