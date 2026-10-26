# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [0.8.30] - 2026-10-26

### benchmark v1 脚手架（C 类可扩展项）——把"看起来对"变成可复现的一致性数字

补齐 `docs/benchmark-plan.md` 列为缺失的可报告基础设施，**零运行时依赖、全离线**：

- `benchmark/agreement.py` 升级：
  - `bootstrap_kappa()` 用纯 Python 算 95% CI（numpy 不可用也不引入依赖），
    `--bootstrap / --seed` 可复现——plan §3「永远报 CI、不报单点估计」落地。
  - `--datacard` 自动导出 markdown 数据卡（样本量 / 双标注比例 / kappa+CI /
    分能力表 / 引擎-人工 / 分歧样例 / 复现命令）。
  - `--consensus` 导出仲裁用标签：一致项 `needs_review=False`；分歧或单标注项
    `needs_review=True` 并保留 `raw_a / raw_b`，第三轮仲裁不丢原始判断。
  - 顺手修了 `--engine` 路径的老 bug：`matching.match` 返回 `(matches, used)` 元组，
    旧代码直接 `.get()` 会崩（因 cases_v0 无标签从未被走到）。
- `benchmark/annotate.html` 加双标注对比模式：载入第二标注人 JSONL，分歧项红框 +
  `B: …` 标签高亮，实时「分歧 N / 双标注 M」计数；对比逻辑抽成纯函数
  `computeDisagreements`（冒烟里真测，还抓出并修了「两人都标时重复计数」的 bug）。
- `benchmark/build_v1.py`：`plan`（300 对 / 30 族目标）、`scaffold`（空槽位，明确
  TODO，绝不伪造 JD）、`validate`（族覆盖 + 双标注就绪 + 未就绪检查）。
- `benchmark/datacard_template.md`：数据卡模板（数值自动填，叙事/法律手工填）。

锁：单测 **231 → 238**（新增 7 条 agreement 测试：kappa 已知值 / bootstrap 确定性 /
CI 含点估计 / 空对 / 数据卡段落 / 共识标记）；`smoke_web` 新增 annotate.html
隔离进程自测（4 项）。真实标注数据仍需人工/志愿者提供（不伪造）。

## [0.8.29] - 2026-10-26

### 网页报告可导出 PDF / 打印（C 类可扩展项）

给网页 demo 的报告加了「导出 PDF / 打印」按钮（单岗匹配区 + 批量区各一个）。
零依赖：走浏览器原生打印（Ctrl/⌘+P 的「另存为 PDF」），不引入任何 JS 库，
契合项目"零核心依赖"的定位。

实现要点：
- 抽出一个共享的 `getReportData()`，Markdown 导出与 PDF 打印**共用同一份数据源**，
  避免两份渲染逻辑漂移（这正是之前"网页 vs CLI 能力差"的教训）。
- `buildPrintHtml()` 是纯函数，把报告拼成一份干净的、带打印样式（`@media print`）
  的可打印 HTML——屏幕上看不到，只有打印/导出 PDF 时才显现，且页面其余部分被隐藏。
- 用户投递内容（JD / 简历）经 `esc()` 转义后再进 HTML，防 XSS（与看板 `<script>`
  转义同一纪律）。
- `window.print()` 在 Node 测试桩里做了 `typeof` 防御，不会因测试环境缺 `window` 而崩。

锁：`scripts/smoke_web.py` 新增 `buildPrintHtml` 自测（喂合成数据，断言无 `undefined` /
`NaN`、含关键标题），网页冒烟 **18 → 19 个入口**全绿；词表同步无漂移。

## [0.8.28] - 2026-10-26

### hr 词表文档级语境约束（B1）——把"已知弱点"变成"已修弱点"

沿用 v0.8.13 的 `CONTEXT_REQUIRED` 机制（engineering / adm_archive / domain /
product_sense 已验证 44%→92% / 8%→92%），把同一套路用到 `hr` 族四个子族
（`hr_recruit` / `hr_perf` / `hr_training` / `hr_labor`）。

根因比设想更深：中文 JD 里「培训 / 绩效 / 薪酬 / 激励 / 招聘 / 用工」是**全员通用模板词**
（任何岗位都写"提供培训 / 绩效奖金 / 五险一金 / 我们正在招聘"），单独出现不等于人力岗。
所以语境表只列**岗位专属复合词**（培训体系 / 招聘渠道 / 薪酬管理 / 员工关系 / 劳动关系 /
组织发展…），不用「员工 / 入职 / 社保」这类同样全民通用的词（否则门控等于没拦）。

门控后实测（1,838 条真实中文 JD）：hr 假标签 **708 → 226（-68%）**、any-hr 检测精确率
**2.7% → 8.4%**（招聘 8.8%→20.0%、绩效/薪酬 1.6%→6.4%、培训 2.0%→7.7%），**hr 族召回
19/21 零损失**、45 条人工标注集仍 100%、中文族识别 **0.860 零回归**。

配套：加 7 个反向回归单测（泛词单独出现不触发 / 强语境出现必触发 / P33·P34 边界正例仍命中）；
`培训赋能` 与 `培训及考核` 两个低频短语进 hr_training 语境表救 P33/P34；
网页词表由 `sync_web_vocab.py` 自动同步、跨引擎三套比对全绿；单测 224 → **231**；
版本号三处一致锁提到 0.8.28。

残余误吸属语义层面（真 HR 岗在中文数据占比极低 ≈1%），归 LLM 路线——证据墙如实降级标注。

## [0.8.27] - 2026-10-26

### 补上 CI 里缺的三道检查（体检清单 P1）

体检时列的三处"承诺在、验证不在"里，最后两处在这版补掉：

1. **console script 从没被按用户的方式试过**——CI 一直只跑 `python -m career_loop`，
   等于没验过 `pyproject` 里那个入口。现在装完就敲 `career-loop --help`，
   并且再跑一次会读数据的 `career-loop occupations`（只解析参数表不算验证）。
2. **看板是唯一依赖可选第三方包的部分，CI 完全不回归**——新增独立 `ui` job
   （不塞进 6 个矩阵 job，免得每个都装一遍 streamlit）：
   `pip install -e .[ui]` + `smoke_dashboard.py --strict`（无头 AppTest，不开浏览器）
   + `--self-test`（确认这个冒烟自己也有牙齿）。
3. **顺手拆掉一颗我自己刚埋的雷**：docker job 里断言 `occupations | grep "49%"`，
   v0.8.26 把口径改了之后这个数字变成 78%——**用具体数字断言，等于在验证
   "我没改数字"而不是"命令能读到数据"**。改成断言文字标签「词表覆盖」。

已知遗留：看板里 `use_container_width` 已被 streamlit 标记废弃（计划在 2025-12-31
后移除，目前 1.66 仍可用，只是告警）。没有立刻改签名——新签名 `width=` 会打破
`streamlit>=1.30` 的下限兼容；这条由新增的 `ui` job 看着，真移除时 CI 会先红。

仓库唯一长期未解决项仍是 **P0 GitHub 推送**：本机到 github.com 不通
（代理隧道 502，之前是 hosts 被指向 127.0.0.1），换网络后
`bash scripts/publish_github.sh` 即可，脚本本身已自检过。

## [0.8.26] - 2026-10-26

### 把「覆盖面」的分母换成别人给的：职业分类对账重写 + 三个新行业词表

体检清单的 P5（唯一一项"真正扩能力"而不是还技术债的）。

**1. 先修口径：分母不能自己挑**
旧版对账只整理了 39 个中类，而且**每个都有词表**，于是算出两个都"对"、但都没
回答问题的数：100%（分母＝我自己挑的那 39 个）+ 49%（39/79）。

- 现在把大典目录**按编号整理进来**（1-01 … 8-00，共 76 个可核对的编号），
  分母固定为官方的 79，重新给出三口径：
  - **词表覆盖 62/79 = 78%** ← 头条，分母是大典全量；
  - 完整度 62/76 = 82%（分母＝我按编号整理出来的）；
  - **目录整理度 76/79 = 96%** ← 坦白这份清单本身也没抄全，不是 100%。
- 78% 里的大头不是新词表，是**把已有词表认领到了此前没认的中类上**
  （6-18/6-19/6-20/6-21 机械制造类、6-04 纺织、4-05 金融服务……本来就支持，
  只是从没在大典这张表上登记过）。**这是记账问题，不是新能力**——所以下面
  单独说真正新增的部分。
- 中类编号与名称整理自公开的大典目录（大类 8 个 / 中类 79 / 小类 449），
  模块 docstring 明写"启发式整理、非官方逐条数据"；早期版本给
  「信息传输、软件和信息技术服务人员」自己编了个 2-11（它实际是 **4-04**），
  这种编造编号已纠正。

**2. 真正的新能力：三个行业词表（69 个族 / 180 个能力项）**
候选词先在 8,674 条真实中文 JD 上逐词审计（`scripts/audit_new_pack_words.py`）：
- `maritime` 船舶/航运（对应 2-04 船舶方向、6-23 造船方向）
- `mining` 采矿/地质（对应 6-16 采矿人员）
- `environment` 环保/EHS/双碳（对应 4-09 水利环境公共设施、6-27 再生资源）

**3. 这次踩的两个坑（都是方法论级别的，记下来免得重犯）**
- **不能用「正文含该词」定义目标集，再来统计该词的判别力。**第一版这么干，
  挖出来的候选精确率清一色 **1.00**——因为目标集就是这个词定义的，纯自证。
  **目标集必须由与正文无关的东西定义**（本轮用岗位名）。
- **不收裸名词。**初版收了裸的「船舶」，结果真实 JD 的
  「任职要求：船舶制造类相关专业」被判成"具备船舶营运操作能力"——
  匹配的是字面出现，不是能力（eval_real_jd 的负例 N07 就是这么被抓出来的）。
  改成复合词（船舶营运调度 / 船级社 / 尾矿库 / 环境影响评价…）后回归干净。
  同时把因此过时的标注 N06 改标为正例（新增词表后它确实是能力要求），
  负例名额补同等数量，样本量不减。**改标注不改引擎。**

**4. 必须说清的能力边界（不夸大）**
这份中文数据集是白领/互联网向的——新三族的复合词在里面命中极少（多数词 0~3 条），
**所以不宣称"数据验证过的召回"**。能宣称的是：不误伤（复合词 + 反例/负例测试
都绿）与语义合理性。候选阶段被刷掉的方向（航空、半导体、印刷包装）这轮
**没有**化成词表，也不对外宣称——审计里它们的岗位名同职业比例只有 0~33%。

自检：单测 216→**224**；`scripts/audit.py` 41/41；**中文族识别 0.860 无回归**
（1581/1838，与改前逐条一致）；跨引擎三套全绿；网页冒烟 18/18。
新增锁：`test_referenced_packs_actually_exist`（对账表引用的族必须真的存在——
这条是自己的疏漏催出来的：曾先把 maritime/mining/environment 写进对账表，
而引擎里还没有这三个族）、`TestNewIndustryPacks`（7 条，含裸名词禁令）。

## [0.8.25] - 2026-10-26

### 网页与 CLI 的能力差：`daily` 和 `occupations` 上墙，并锁死不会漂移

体检清单的 P4。网页 demo 长期以来比 CLI 少两块能力（`daily` / `occupations`），
这次补上；但真正值钱的不是"又多了两个按钮"，而是**补完之后两边不可能各说各话**。

**1. 网页新增两块（都不自己算算法，只渲染 Python 同步过去的结果）**
- 「批量岗位」区块加「③ 按今日清单排序」+ 三种格式导出：先到期先投，和
  `career-loop daily` 是同一条排序规则。
- 新增「职业分类 · 覆盖面对账」区块：**映射完整度 39/39** 与 **覆盖广度 39/79 = 49%**
  两个数字在同一个通栏里，避免再出现"只引用 100%"的口径误导。
  网页不做任何计算—— summary 由 `sync_web_vocab.py` 生成进去，
  所以"网页看到的"和"CLI 跑出来的"在结构上就是同一个数。

**2. 新增 `scripts/cross_engine_daily_check.py`：启发式最容易两边写两遍**
截止日解析是启发式，22 条边界文本（标准写法 / 英文 deadline / 点分隔 / 同句既有日期
又有"招满为止" / 发布日期与公司成立年份不该被抓 / 非法日期 2 月 30 / 短日期过期推明年）
逐条比对 Python `find_deadline` 与网页 `findDeadline`，**连同"没日期"的来源文案一起比**。
已进 CI 与单测。

**3. 顺手被这次对拍抓出来的两个真问题**
- `daily._first_date` 的兜底分支写成 `_mk_date(today.year, month, day, today)`——
  `_mk_date` 只收 3 个参数。这条分支要走到，得先构造出一个两年都不合法的日期
  （如 2 月 30 日），所以手点页面碰不到，但只要碰到就是 TypeError。
- `TestCrossEngineConsistency.test_cross_engine_check_passes` 里仓库根少算一层
  （`parent.parent` 而不是 `parent.parent.parent`）→ 脚本永远找不到 → 永远 `skipTest`。
  **一条假装通过的一致性锁比没有锁更糟**，现在缺脚本直接判定失败而不是跳过。

**4. 为跨引擎一致，正则故意写丑一点**
`_DATE_SHORT` 从 `(?<!\d)` 改成 `(?:^|[^0-9])`：**JS 的 lookbehind 到 Safari 16.4 才支持**，
用了它，老 Safari 上 `new RegExp()` 直接抛错、整页功能全挂。Python 侧 17/17 行为不变。
（代价是 pattern 不那么直观，代码里写明了原因，免得有人"顺手改回去"。）

**5. 纯函数全绿 ≠ 页面能用，所以补了整页冒烟 `scripts/smoke_web.py`**
前面的问题都是纯函数层面的比对发现的；但比对只验到函数返回值，**页面照样可以是
坏的**。把整段 `<script>` 加载进 Node、挨个点过每个入口之后（18 个），又冒出三个
真实缺陷：
- **`OCC_SUMMARY` 漏导出 `big_classes`** → 网页第三张指标卡当场印 `undefined`。
  （顺手把 summary 的比对改成枚举全部 key，不再"挑几个比"。）
- **「先点③今日清单、再点导出报告」会抛 TypeError**：`exportReport()` 是从 DOM
  读标题/缺口的，而今日清单的卡片没有 `.job-gap`，写死的 `.textContent` 直接炸，
  结果是什么都没下载。改成 `_txt()` 取不到就给空串，并按当前视图换标题。
- **网页的岗位名带着 Markdown 的 `#`**（"# Agent 应用开发工程师"），而 CLI 那侧是
  干净的（Python `extract_title` 会剥）。同一个产品两种叫法最伤信任 → 对齐，
  并把岗位名也纳入跨引擎比对（Python `extract_title` ↔ 网页 `titleOf`）。

自检：单测 212→**216**；`scripts/audit.py` 41/41；跨引擎三套全绿
（能力项 51/51、LLM 四后端、daily 22 条 + 岗位名 + 职业分类 summary）；
**网页端到端冒烟 18/18**，且它的 `--self-test` 要求四种注入坏法全被抓到
（漏字段 / DOM 不判空 / JS 语法错 / 岗位名忘了剥 `#`），跑完还要把 index.html
还原成原样（有单测盯着，免得自测污染工作区）。

**6. 两个检查脚本都得自证有牙齿**
- `cross_engine_daily_check.py --self-test`（不需要 node）：注入四种偏差——
  日期差一天、来源文案不一致、网页给了 CLI 没给、CLI 给了网页没给——
  **每一条都必须被判成不一致**；外加校验从 HTML 里抠出来的 JS 真的含有
  `findDeadline` 与全部同步常量（否则"看不到"和"一致"会被混为一谈，
  历史上漏抽过 const 包装常量）。

## [0.8.24] - 2026-10-26

### 体检：把「README 承诺的能力」和「实际能跑的命令」逐条对一遍

一次全仓库体检的结果。21 个命令逐个真跑了一遍（不是看 `--help`），
自检全绿，但**全绿不等于没缺口**——下面两处都是"承诺在、入口不在"。

**1. `taxonomy_cn.py` 是死代码，而它背着一个对外承诺（已修）**
README 两处写"岗位族可对齐到《职业分类大典》8 个大类（见
`career_loop/matching/taxonomy_cn.py`）"。但全仓库零引用：
`coverage_matrix() / render_coverage()` 实现完整，没有任何命令能把它跑出来。
评审照着 README 找不到入口，只能读源码——能力不是写错的，是**没有入口**。

- 接出来：`career-loop occupations [--out FILE]`，输出对账表。
- **顺手拆掉一个口径陷阱**：模块算出来是 39/39 = 100%，而这个 100% 读起来像
  "覆盖了大典全部中类"——实际只是"我收录的都建了词表"，大典有 79 个中类，
  还有 40 个完全没有词表。现在 `coverage_summary()` 同时返回两种口径
  （**映射完整度 39/39** vs **覆盖广度 39/79 = 49%**），渲染结果与 CLI 输出
  都强制两者同屏出现，有单测锁住"改文案也别把 79 改没了"。

**2. CLI 能记的状态比回流口径窄（已修）**
`career-loop log` 只认 5 个状态，而 `reflow` 定义了 7 个。缺的两个恰好是关键：
`interview_eliminated`（进面试但淘汰）是 terminal 口径专门从"简历关拒绝"里
拆出来的中间态；`silent`（超期无反馈）是数量往往最多的一档。
走 CLI 闭环的用户记不了前者，只能记成 `rejected`——含义完全不同。
另外 `reflow --db-write` **写进库里的就有这两个状态**，等于 `log` 改不回来。

- `log --status` 改为随之扩展（`status` 是纯 TEXT，无需迁移），
  新加 `TestStatusEnumParity` 锁住 CLI / reflow / DB 三处枚举逐条一致。
- 顺手修 `career-loop status` 输出被 20 字符的长状态挤到列读不清（动态列宽）。

**3. 把这类缺口变成不可能再发生**
新增 `test_every_cli_command_is_documented`：双向比对**已注册命令**与**两版
README 里出现的命令**，缺一边就红。它当场抓到刚加的 `occupations` 还没写进文档。
A/B 自测 3/3（删光提及 / 写不存在的命令 / 拼错命令名都必须红，真实文档绿）。
首版全文正则把英文散文里的 "career-loop web demo:" "career-loop also asks…"
当成命令（两条假阳性）——限定到**代码块行首 + 内联反引号**两种位置后干净了；
一个会误报的检查脚本很快就会被 ignore，所以这一步不能省。

自检：单测 192 → **202**；`scripts/audit.py` 40 → **41**（`occupations` 必跑，
且断言输出含 `39/39` + `49%` + `启发式`——只查返回码等于没查）；
词表同步 / 跨引擎一致性仍全绿。

## [0.8.23] - 2026-10-26

### W16：每日投递清单——今天先投哪个、投之前改哪一句

README 的 W4 从很早就挂着「每日清单待做」，这次落地成一条命令：`career-loop daily`。

它回答的是比「我适合哪个岗」更具体的问题——**今天先投哪个、投之前先改哪一句**。

**每行四样东西，缺一样就不是清单、只是一份排行榜**

岗位 + 匹配分 + **最划算补强** + **截止日**。「补强」不是一句建议，是调用
`counterfactual` 真的重算一遍「补上之后几分到几分」，所以清单上写的是
「66.7% → 76.2%（+9.5）」这种能当场决定要不要动的数字。

排序：**有截止日的先按截止日升序**（先到期先投），没截止日的排后面、内部按匹配分降序；
每行还带一句「为什么排在今天」（距截止几天、补哪一项能涨多少）。
`--min-score` 先砍掉明显够不着的，`--due` 给整批兜底一个统一截止日。

**导出要能进别的地方**：Markdown 勾选清单（贴进笔记 / 滴答清单）、
CSV（进表格 / Notion 数据库）、**ICS**（VTODO 带 `DUE;VALUE=DATE`，能直接进日历
与待办 App）。用 VTODO 而不是 VEVENT：投递是一件**要做的事**，不是一段占用的时间。

**截止日是启发式，所以每条都必须写来源**

只在「截止 / deadline / 有效期至 / 报名截止」等线索词附近的 60 字窗口里找日期。
抓到就标「JD 原文」，`--due` 兜底标「命令行统一指定」，JD 没写标「JD 未给出」，
遇到「招满为止」明确说「JD 写的是『招满为止』，没有具体日期」——
**把猜出来的日期伪装成确定的，是这类工具最坏的 bug**，所以宁可漏、不准装。
发布日期、公司成立年份这类数字不会被误抓（单测里有这两条负例）。

**踩到并修掉的一个真 bug**：`截止日期：2027-02-28（招满为止不做另行通知）`
被判成「没有截止日」。原因是最初先把「招满为止」当成一个独立的短路分支，
而真实 JD 里这两种写法经常同句出现——结果是**静默丢信息**（清单上少一条截止日），
比猜错更隐蔽。修法是把「招满为止」的判断挪到找完日期之后，
并由 `test_real_date_wins_over_open_ended_in_the_same_sentence` 锁住。

自检：单测 175 → **192**（新增 17 条，日期解析的边界占多数）、
`scripts/audit.py` 32 → **40**（三种导出都要跑得通且文件非空 + 坏截止日被拒）。

## [0.8.22] - 2026-10-25

### W15：看板做实——把「一个 r」升级成「一条带置信区间的判据」

README 早就写了「可选看板」，实际却只有一张分桶柱状图和一个明细表。
这次把它做成承诺里说的那三块：**投递漏斗 + 匹配分×正反馈散点（含置信区间）+ 缺口排行**。

**为什么给 r 加置信区间（`calibrate.pearson_ci`）**

一个孤零零的 r 是没法证伪的：n=12 时能跑出 +0.293，换个 seed 可能就是 -0.2。
现在用**成对 bootstrap**（固定种子 → 同一份数据每次同一结果，可写进单测）
给出 95% 区间，判据只有一条：**区间跨不跨 0**。演示数据的区间是
`[-0.280, +0.854]`，跨 0 → 「这份数据不能排除『匹配分和结果毫无关系』」。
样本 < 8 时**直接不给区间**——那个量级下任何精度都是假的。

**新增数据层 `career_loop/dashdata.py`（零第三方依赖，20 条单测）**

看板的计算不写在 `dashboard.py` 里，是因为这类 bug 有个共同特点：
**图照样画得出来**。漏斗顺序错了、口径判错了、异常被降级成一句 caption 了，
屏幕上都是一张正常的图。抽出来之后可以断言：漏斗=口径常量顺序、
`interview` 在 early 是正反馈但在 terminal 不是、抖动可复现、
注入的 `<script>` 被转义（`_esc`，导出 SVG 分享时就是 XSS 载体）。

三种数据源：显式记录文件 > 本地 SQLite > 演示数据。
演示数据是**编造**的这条信息放在 `BoardData.warnings` 里，看板顶部红字躲不掉。

**图表自己画 SVG，不引 pandas/altair**：少一层版本兼容问题，
而且图前后或不失去指标定义——口径、样本量、置信区间直接写进图，
截图发出去不会丢上下文。

**新增 `scripts/smoke_dashboard.py`**：用 AppTest **不开浏览器**跑一遍看板，
能抓住 `streamlit run` 特有的相对导入失效和 API 变更；自带 `--self-test`
（喂坏代码必须报错），不是那种只会说"通过"的检查脚本。

**顺手修掉两个真 bug**

- `store.py` 异常路径没关 sqlite 连接 → Windows 上库文件被锁删不掉
  （单测里 WinError 32 抓到的）。改成 `_fetchall/_fetchone` 统一 `finally: close()`。
- `recommend.gap_leverage` 的自定义能力项显示成一串 MD5（「custom:6f4c28c5」），
  CLI `recommend` 和看板都受影响；现在回退到 JD 抽出来的原文标签。

单测 155 → **174**；`scripts/audit.py` 32/32；跨引擎 LLM 检查四项全绿。

## [0.8.21] - 2026-10-25

### W14：网页版接入 LLM 族识别（本机代理）

让**评委打开网页就能看到项目最强的能力**（规则 86.0% → 规则+模型 93.4%），
而不是只能在 CLI 里看到。

**新增 `career-loop llm-proxy`（`career_loop/llm_proxy.py`，零第三方依赖）**

浏览器直连模型服务商有两个绕不开的硬障碍：多数 OpenAI 兼容服务不给
`Access-Control-Allow-Origin`（CORS，浏览器直接 fetch 被拦），以及 API Key
不该进网页表单。这个代理跑在**本机 127.0.0.1**，Key 留在本地环境变量 / `.env`，
网页只跟本机说话——两个障碍一起解决。

安全设计（11 条单测逐条锁住）：只绑回环地址 / 启动生成一次性 Token（防本机
其它网页盗用 Key 去计费）/ 请求体上限 200KB / **不接受网页指定模型**（防被指向
更贵的模型）/ Origin 默认只放行 `file://` 与 `localhost`。

**修掉一个真 bug**：请求体超限时服务器在客户端还没发完就回应并断开，
客户端拿到的是 `connection reset` 而不是 `413`。修法是先读掉请求体再回应，
并由 `test_oversized_body_is_rejected_without_connection_reset` 锁住。

**网页端**

- 「中文抽取实验室」新增「接入 LLM 族识别」面板：填代理地址与 Token →
  「测试连接」看模型/上游/有没有 Key → 「用模型判族」得到模型族 + 规则族 +
  混合结果（紫色=模型判出，青色=规则补充）。
- 网页的 `normalizeFamilies` / `blendFamilies` 镜像 Python 的 `_normalize` 与
  blend 规则（模型首选优先、规则补后面保召回）。
- 失败可见：代理没起 / Token 错 / 模型返回非法 JSON 都有明确提示，
  且**规则基线的结果始终有效**。

**两端一致性（新增 `scripts/cross_engine_llm_check.py`）**

`sync_web_vocab.py` 现在额外同步 `FAMILY_PROMPT`（2429 字符，与 Python
`family_system_prompt()` 逐字一致）与 `FAMILY_KEYS`（67 个）。
新脚本再逐项校验：提示词逐字一致 ✓ / 归一化 16/16（含中文名回映射、大小写、
重复、非法 key、非字符串、ai_* 父族推导、空输入、非列表等边界）/ blend 6/6 /
合法族 key 集合 ✓。

**真实端到端实测（非模拟）**：浏览器 → 本机代理 → deepseek-flash → 回传 →
归一化 → 混合 → 渲染，客服 JD 得到「模型判出 1 个族（客服）· 规则判出 2 个 ·
混合后 2 个」——模型判出的正是 W9 证明词表补不动的 service 族。

**文档**：README（中英）新增 llm-proxy 用法与网页面板说明；evidence.md 新增
1.7 节记录设计、踩到的 bug、一致性数字与四条诚实边界；
网页证据墙的 LLM 区块补一段说明。

**回归**：单测 144 → **155**（+11 代理测试），audit 32/32、词表同步无漂移、
跨引擎 51/51、LLM 族识别跨引擎四项全绿。

## [0.8.20] - 2026-10-25

### W13：英文 README + 仓库页打磨（星标与投稿的地基）

**新增 `README.en.md`（639 行）**

不是机翻——把「匹配分是可被证伪的」这个核心概念用英文重新讲了一遍，结构对齐中文版：
首屏差异点 / 做什么不做什么 / 与同类项目对照表 / 六步闭环 / 功能清单 / 安装 /
可选 LLM / 快速开始（四段可复制命令 + 真实输出）/ 任意岗位族覆盖 / 三支柱评测体系 /
仓库结构 / 质量自检 / 设计取舍 / 已知局限 / Contributing / License / 相关项目对照。
英文 README 顶部有 4 枚徽章（含新增的 `tests 138 passing`），中英两版互链。

**`docs/repo-page.md`（仓库页配置清单）**

仓库的 description / Topics / 社交预览图 / Features 开关 / 分支保护属于**账号侧一次性
配置**，写不进代码，所以做成一页可直接照抄的清单：
- Description 两条候选文案（含关键词覆盖说明）
- 13 个 Topics（含为什么要加 `llm`、为什么不堆 `ai`、为什么加 `falsifiability`）
- 社交预览用 `docs/og-cover.png`，附检查点
- Features 开关逐项建议（Issues/Discussions 开，Wiki 关——避免第二份不同步的真相）
- `main` 分支保护规则（PR + 必过 CI）
- 发布后 48 小时内的三件事 + 第一个 star 的三个转化来源

**顺带修正的不精确表述**

- 演示视频实际 **135.0 秒 = 2 分 15 秒**，两版 README 与投稿包此前都写"3 分钟"
  （链接文字与 W8 条目）。标题改为真实时长，锚点同步更新。
- 补齐 5 处中英不对称：留出集 86.2% → 100.0%、中文集全量 8,674 条，
  以及**作者私有失效区间 r = -0.059 / 终局 r = 0.03**（此前只在 evidence.md，
  现在进了两版 README 的显眼位置——这是项目最独特的招牌）。

**把一致性做成回归锁（新增 6 个单测，`TestDocsConsistency`）**

这个项目的纪律是「数字必须和引擎真实值一致」，而两份 README 极易各改一边、悄悄漂移：

- `test_key_numbers_appear_in_both_readmes` — 33 组关键数字必须同时出现在两版
- `test_internal_anchors_resolve` — 目录锚点必须真的指向某个标题
- `test_referenced_files_exist` — 引用的本地文件必须存在（防 404 链接）
- `test_readmes_cross_link_each_other` — 两版必须互链
- `test_video_duration_claim_is_consistent` — 不允许再写"3 分钟"
- `test_english_readme_exists` — 英文 README 不许被删

**测试自身已做 A/B 自测**（沿用 `audit_anonymization.py` 的规矩）：
把英文版 93.4% 改成 94.0% → 报 `数字不对称：['93.4%']`；
把中文版 10,613 改成 10613 → 报 `数字不对称：['10,613']`；还原后全绿。

**回归**：单测 138 → **144**，audit 32/32、词表同步无漂移、跨引擎一致。

## [0.8.19] - 2026-10-25

### W12：上架前终检 + 一键发布脚本

**终检发现并修掉的问题**

- **分支 `master` → `main`**：CI 的 `triggers` 只监听 `main`、pyproject 的文档链接指向
  `/tree/main/`、Pages 配置源是 `main` —— 原先本地是 `master`，**CI 永远不会触发**。
- **评测集生成脚本与数据集脱节（真 bug）**：`scripts/gen_eval.py` 只能造 42 条，而
  `data/eval_sample.jsonl` 已有 60 条（后 18 条是 W6 手工补的通用能力 / 边界样本）。
  任何人跑一次生成脚本都会把评测集砍掉 18 条、悄悄改动基线。已把 18 条补回脚本，
  现在生成结果与仓库文件内容一致；脚本同时从根目录移到 `scripts/`（修好相对路径）。
- **过时数字勘误**（用当前引擎重算，非手改）：README 三处「50 条评测集」→ 60 条；
  `docs/benchmark.md`「评测集 50 条」→ 60 条、SALES 69.8% → **78.4%**
  （v0.8.7 补判别词后的真实值，由 `scripts/real_eval_family.py` 实跑确认）；
  路线图标题「W4–W8 进行中」→「W1–W11 已完成」，补 W9 / W10 / W11 三条。
- `pyproject.toml` 版本 0.8.13 → 0.8.18；新增 `docs/.nojekyll`（Pages 部署保险）。

**新增**

- `docs/benchmark.md` §2.4：把 W10 的 LLM 族识别对照（rules 86.0 / llm 86.5 /
  auto 87.0 / **blend 93.4**，含 top-1 与平均族数）写进「可复现数字」文档，
  注明 ±0.1pt 波动来源、¥9 成本、以及主链路不接 LLM 的产品决策。
- `scripts/publish_github.sh`：一键发布脚本——网络体检（github.com 可达性 +
  DNS 污染诊断）→ 本地体检（工作区干净 / 密钥扫描 / 站点根就绪）→ 认证检查
  （gh CLI 或 `GH_TOKEN`）→ 创建 public 仓库 → 推送 `main` → 开 Pages
  （`main` / `/docs`）→ 访问自检。凭证只从 `gh auth login` 或环境变量读取，
  **不写入任何文件、不打印**。

**回归**：138 单测、audit 32/32、对照集一致率 1.0、英文族识别 93.6%、
中文族识别 86.0%、抽取 45/45 + 留出 100.0%、跨引擎一致、脱敏审计干净。

## [0.8.18] - 2026-10-25

### W11：投稿材料打磨（1024 造物挑战）+ GitHub ID 勘误

**数字勘误（用当前引擎重算，非手改编数）**：

- 作者私有 40 条投递 early 口径 r = -0.255 → **-0.059**（重跑
  `career-loop reflow --records data/calibration/applications.json --mode early`；
  分桶：20-40 档 30% / 40-60 档 27.3% / 60-80 档 15 条 0% / 80-100 档 50%）
- 50 条同源样例 terminal 口径 r = 0.003 → **0.03**；
  `docs/reflow_sample.md` 由 `scripts/make_reflow_sample.py` 重新生成
- 波及：evidence.md（第 3 节整表 + 总览 + 收尾）、submission.md、share-kit.md、
  retro.md、index.html（rf-stat / RF_BUCKETS / 证据墙卡 / 失效区间行）、
  reflow_sample.md（重新生成）。CHANGELOG 历史条目保留旧值，以勘误表为准
- retro.md 补「打脸之后」一节（W7–W10：中文 86.0% / 补不动的证据 / blend 93.4% /
  主链路不接 LLM），删除已过时的「下一步 42→50 条」

**素材重制（旧素材数字停留在 v0.4 时代）**：

- `docs/demo.gif`：用当前 CLI 输出重录（80.4% / 63.6% / 43.2%）
- `docs/demo.png` / `docs/demo-finance.png`：当前网页重截图（66 岗位族 / 60 评测集 /
  v0.8.17；会计岗 81.8% 持久准确）；hero 统计条 65→66 族、42→60 评测集、版本号 v0.4→v0.8.17
- `docs/og-cover.png`：同版式重绘（65→66 岗位族）
- `docs/career-loop-demo.mp4`：按当前引擎数字重制（135s，H.264 716KB）——
  校准段改用同源样例数据真实值 r=0.03 并**明确标注数据性质**（原视频的 r=0.694
  是编造演示数据且画面无标注，属可证伪性风险）；证据墙新增 blend 93.4%

**GitHub ID 勘误**：用户 2026-10-25 明确 ID 为 **jian935**（此前误记为 jian35），
全仓库 26 处链接统一替换（README / pyproject.toml / docs/index.html /
submission / share-kit / retro / fetch_real_eval_data.py / CHANGELOG 历史行）。
对外链接：`github.com/jian935/career-loop`、`jian935.github.io/career-loop`。

**校验**：138 单测全过、audit 32/32、词表同步无漂移、跨引擎 51/51。

## [0.8.17] - 2026-10-25

### W10：LLM 族识别后端——1,838 条真实调用，五种模式同台实测

1.5 节结论指向语义模型，本轮就是这条路的落地与实测。核心数字
（同一数据集 / 同一标签 / 同一输入字段，岗位名不喂模型）：

| 模式 | 做法 | any-in | top-1 | 平均族数 |
|---|---|---|---|---|
| rules | 纯词表（原基线） | 86.0% | 56.6% | 4.88 |
| llm | 纯模型 | 86.5% | 73.5% | 2.20 |
| auto | 规则先判，空结果才问模型 | 87.0% | 57.6% | 4.90 |
| **blend** | **LLM 首选优先 + 规则补充** | **93.4%** | **73.5%** | 5.49 |

- **W9 补不动的两族补动了**：service 52.2%→78.3%、project_mgmt 69.8%→82.5%；
  两个引擎盲区几乎不重叠（规则漏短 JD / 同义表达，LLM 漏咨询 / 实施 / 售前）。
- **LLM 单独用不是规则替代品**：consulting 77.5%→28.1%、it_systems 84.5%→32.1%、
  ai_solution 82.2%→21.9%——「实施顾问」类 JD 被模型判成 sales/service，
  与 W9 的标题-正文矛盾同源。
- **新命令** `career-loop domains --file jd.md --backend blend|llm|auto|rules`；
  未配 Key 或调用失败一律回退规则并标注原因（`used` / `note`），
  主链路（match / whatif / reflow / calibrate）**不接** LLM——校准 r 必须离线可复现。
- **复现**：`scripts/llm_family_eval.py`（1,838 条真实调用，deepseek-flash，
  1 次 HTTP 失败 0.05%，墙钟 517s ≈ ¥9；原始预测落盘 `data/llm_eval/`，gitignore）。
- **诚实边界**：LLM 数字跨运行 ±0.1pt（temperature 0.2 + 数据集 383 条重复正文
  在并发下同文不同答）；缓存保证同一次运行可精确复现。详见 evidence.md 1.6 节。

### 工程

- `career_loop/matching/family_llm.py`：族提示词封闭集（66 族 key + 中文名 + 代表维度，
  单测锁「FAMILY_CN 必须恰好覆盖词表族 + ai 父族」）；镜像规则的 ai_* → ai 父族推导。
- `FAMILY_CN` 从 `cli.DOMAIN_CN` 下沉到 `schema.py`（单一来源，`sync_web_vocab` 经别名不受影响）。
- `LLM` 客户端新增 `stats`（http_calls / cache_hits / failures，锁保护）——
  评测脚本据此如实报告「实调 vs 缓存」，原来把缓存命中也报成「实调」。
- 单测 124 → **138**；全量回归零回退（audit 32/32、对照集 100%、英文 93.6%、
  中文 86.0%、抽取 45/45 + 留出 100%、跨引擎 51/51、脱敏审计干净）。

### 数字勘误（投稿材料打磨时发现，全部用当前引擎重算替换）

按「对外引用的 r 必须是当前引擎真实值」纪律，用 `data/calibration/` 私有数据
（不入库）重跑 `career-loop reflow` 后更新：

| 位置 | 旧值（引擎修复前） | 当前引擎真实值 |
|---|---|---|
| 作者私有 40 条投递（early 口径） | r = -0.255 | **r = -0.059**（正反馈 7/40 = 17.5% 不变；分桶：20-40 档 30%、40-60 档 27.3%、60-80 档 15 条 0%） |
| 50 条同源样例（terminal 口径） | r = 0.003 | **r = 0.03** |

波及文件：`docs/evidence.md`（第 3 节整表 + 分桶 + 总览 + 收尾）、
`docs/submission.md`、`docs/share-kit.md`、`docs/retro.md`、`docs/index.html`
（rf-stat / RF_BUCKETS / 失效区间行）、`docs/reflow_sample.md`（重新生成，非手改）。
历史版本条目中的旧数字保留原样（CHANGELOG 不改写历史），以本条为准。

## [0.8.16] - 2026-10-25

### W9：专攻 service / project_mgmt——四条路试完，确认补不动（证据链上墙）

v0.8.14 后最弱的两族（service 52% / project_mgmt 70%）。本轮**没有为凑数字硬加词**，
四条路逐条走完，每条都有数据，结论写进 `docs/evidence.md` 1.5 节：

1. **单词补词**：去重 + 排除矛盾记录后 service 的 dev miss 仅 8 条、
   project_mgmt 6 条；过 60% 精确率闸的候选 service 只有「组长」
   （上下文是招聘晋升话术，人工过目否决），project_mgmt 一个都没有。
2. **短语级模式**：「售后服务」43.8% 不过闸；**模拟加入后增益为 0**——
   暴露 any-in 判定下的机制：补词的增益上限 = 能救回的 miss 数，
   先量上限能省掉全部后续弯路。
3. **语境约束版**（v0.8.13 机制反向用）：「回访+客服语境」55.6% 最高，
   仍不过闸；没有为好看把闸降到 40%。
4. **人工过目 21 条去重 miss**：约 13 条是标题-正文矛盾
   （标题「客服」正文是销售/工程/招聘话术），真缺口 8 条无合格词。

### 两个数据质量发现（单列报告，不改主口径）

- **标题-正文矛盾 80 条**（占 miss 31.1%、总数 4.4%）：
  `cn_eval_family.py` 新增透明报告节（含实例），主口径不变。
- **重复抓取 383 条（20.8%）**：主口径仍按记录算（86.0% 不变）；
  去重口径 84.6% 作为辅助口径报告（service 52.2%→59.3%）。

### 修掉的挖掘口径缺陷（v0.8.7 起就存在）

`mine_recall_words.py` 的 df 统计改为**按正文去重后**：不去重时 4 条重复抓取
就能伪造「精确率 100%」的候选（df_fam=df_all=4，service 的候选曾全是同一份
「播音配音」JD 的子串碎片）。同时修正：挖掘用的文本一直没剥样板
（与引擎口径不一致，「职位来源于智联招聘」会被挖成候选）。

### 校验

主口径 86.0% 不动（1581/1838）；124 单测、audit 32/32、对照集 1.0/100%、
英文 93.6%、抽取 45/45、跨引擎 51/51 五项全部零回退。
**没有任何词表改动**——本轮的全部产出是诊断、口径修正与证据链。

## [0.8.15] - 2026-10-25

### W8：评测体系上墙（证据墙新增「这些数字是怎么被检验的」常驻模块）

把此前散落在 `docs/evidence.md` 里的检验方法做成网页常驻展示区，回答评审的第一个问题：
**「数字怎么来的、能不能复现」**。纯静态 HTML/CSS，无新增 JS 逻辑。

- **三根支柱卡片**：① 合成对照集 60 条（锁匹配逻辑，明确声明非真实标注）
  ② 英文公开集 1,167 条（族识别 93.6% + r=0.193）③ 中文公开集 1,838 条
  （族识别 86.0% + 抽取 45 条标注 / 10,613 条留出）——每个支柱带数据来源与脚本名。
- **回归护栏矩阵**：10 个检验项 × 当前状态 × 一键复现命令（单测 124/124、
  对照集 1.0/100%、英文 93.6% 不回退、抽取 100%/86.2%、跨引擎 51/51 五项、
  词表同步无漂移、脱敏审计干净、audit 32/32）。
- **方法论三条**（为什么这些数字可信）：dev/hold-out 拆分防过拟合、
  精确率 ≥60% 闸防拍脑袋、标注错了改标注不改引擎。
- **失效区间同样公开**：r=−0.255 / r=0.003 / hr 精确率 5% / service 52%
  与「一条命令跑完全部检验」的复现块。

页面内所有数字与 v0.8.14 实测一致；改动只涉及 `docs/index.html`，
`sync_web_vocab.py --check` 与 `cross_engine_check.py`（51/51 五项）复验通过。

## [0.8.14] - 2026-10-25

### W7：中文族识别 77.8% → 86.0%（先诊断，再动手）

**做法**：没有直接加词。先用两个新脚本定位失败模式——
`scripts/diagnose_cn_misses.py`（空预测 vs 错预测）和
`scripts/analyze_kw_precision.py`（全词表「词→族」精确率）：
- 96.6% 的未命中是**错预测**而非零命中，误输出头号是 hr（326 次）/ admin（303 次）；
- 全数据集按句号切句扫高频样板（出现 ≥150 次即样板），只有两条过线：
  **「职位来源于智联招聘/猎聘/实习僧」**（3,563 条）和
  **「以担保或任何理由索要财物，扣押证照，均涉嫌违法。」**（2,101 条）。
  这两句让「招聘」（hr）在 75%、「证照」（admin）在 41% 的 JD 上假命中——
  **hr 词表精确率仅 2.5%、admin 仅 10.6%**，v0.8.13 里 adm_archive 8% 的根因也是它。
- 弱族缺的是核心词不是边角料：banking/securities 的 99 条 miss 几乎全是
  投资经理/融资总监类岗位，而词表只有银行运营词（信贷/网点），**一个投融资词都没有**。

### 三项改动
1. **修评测标签 bug**（`scripts/cn_eval_family.py`）：TITLE_TO_FAMILY 的 ASCII
   关键词原来按子串匹配，"Abercrombie & Fitch" 因含子串 "cro"（CRO）被标成
   healthcare，4 条服装导购混进医疗族。改为词边界匹配，误标记录剔除
   （1,853 → 1,838 条）。
2. **新增 JD 样板清除器**（`career_loop/matching/boilerplate.py`）：只剥上述两类
   平台固有样板（每条模式都要求出现平台特有措词，宁可漏剥不误剥），
   在 `detect_domains` / `extract_by_rules` 入口剥——用户看到的 quote 也不再带
   免责声明。模式纳入 `sync_web_vocab.py` 自动同步，网页 JS 同步镜像。
3. **弱族词表补充**（每个词先过精确率预检，见下）：banking 新增投行线
   （投行/尽调/投后管理…）、securities 补投资线、**新建 data_analysis 族**
   （此前标签不可达，29 条期望只能靠 ai_data 搭车）、legal 补律所线
   （律师/律所/案件…）、healthcare 补临床线（科室/儿科/门诊…）、
   game/film/operations/energy/agriculture/quality/it_systems/project_mgmt/
   public_admin 按通过清单补词；service 无可过词，**保持 52.2% 不装好看**。

### 防过拟合与防拍脑袋的两道闸
- **挖掘只在 dev 上做**：`scripts/mine_recall_words.py` 把 1,838 条按期望族分层
  拆成 dev（70%）/ hold-out（30%），候选词要求族内 df≥3 且**精确率 ≥60%**
  （精确率 = 出现在本族 JD 的次数 / 出现在所有 JD 的次数，即 v0.8.7 教训里
  「过泛词硬标准」的定量版），再人工过目。
- **增益必须两边都出现**：dev 77.9%→85.9%、hold-out 79.2%→86.2%（+7.1pt），
  hold-out 增益 ≥ dev 增益——过拟合的特征是反过来的（只在 dev 涨）。
  `scripts/measure_split.py` 一键复现。
- **预检拦下 24 个过泛词**（`scripts/precheck_new_words.py`）：「数据分析」
  精确率仅 14%（运营 JD 也到处写）、「客户服务」13.7%、「项目执行」13.3%、
  「巡检」22%——一个都没收。

### 过程中的一次真实回退（如实记录）
admin 从 93.5% 掉到 50.0%：剥样板后现原形——那 47 条「命中」本来就是
「扣押证照」假中的。补了真词（会议纪要/日程/总裁/秘书…）后回到 **87.0%**。
删「接待」（service 词表，精确率 2.4%）前先验证它不是承重墙：
  含「接待」的 3 条 service JD 全部另有「投诉/售后」兜底，删除零召回损失
  （service 36/69 不变）——对照 v0.8.7「直接删词掉 13 个点」的教训，
  这次是**先验证再删**。

### 顺手修掉对照集两个遗留 MISS
「推荐算法工程师」「AI 运营/训练师」命中 ai_recsys/ai_ops 子族却判不出 ai
父族（AI_CORE_KW 不足两个）。改为**任一 ai_* 子族命中即推出 ai 父族**，
对照集已建词表岗位族识别 97% → **100%**，中英文两个评测数字不动。

### 已知局限（不藏着）
- **hr 词表精确率仍只有 5%**（培训 1.9% / 绩效 1.5%）：这些词在各类 JD 的
  福利/考核部分高频出现。不删的原因有数据支撑：删「培训」中文 hr 会掉
  19/21→16/21（3 条培训经理岗只靠它命中）；英文 HR 219/220 靠的是同义的
  英文词（v0.8.7 删 benefits/training 掉 13 个点的教训）。留待后续用
  文档级语境约束解决，本次只把问题记录下来。
- service 52.2% / product 70.4% / project_mgmt 69.8% 仍是短板，
  候选词全部过不了 60% 精确率闸，没有硬凑。

校验：**124 单测全过**（新增 14 条，含样板清除正/反用例、删「接待」的
反向测试、新族识别用例）、合成对照集 60 条 1.0 且族识别 100%、
英文族识别 93.6% 不动、抽取评测 45/45 + 留出 10,613/10,613
（留出集从 10,497 涨到 10,613：新词表让 116 条原本零命中的行变成单命中，
同集合上「关语境约束」对照仍为 86.2%）、跨引擎 **51/51 五项全一致**
（新增「岗位族识别」比对项，JS 的 detectDomains 已镜像 Python 的
样板清除 + AI_CORE_KW + 父族推导）、audit 32/32、词表同步无漂移。

## [0.8.13] - 2026-10-26

### W6 核心：真实中文 JD 抽取评测（评测体系第三支柱）
- 新增 `data/eval_real_jd.jsonl`：**45 条人工标注**（39 正例 + 6 负例），
  文本全部取自公开数据集 `ngtranai09/china_job` 的**真实 JD 行**，覆盖 **20 个能力项**。
  补的是合成短句集（JD 中位 15 字符）测不出的缺口：模板福利条款、学历要求、
  法律声明、跨行内联。
- 新增 `scripts/eval_real_jd.py`：跑标注集 + **留出检验**。
  - 留出集 = 公开集里 **10,497 条从未参与标注**的真实 JD 行，
    判定规则可复核（"只命中一个能力项的行，期望就是那一个"）
  - 有语境约束 **100.0%** / 关掉 **85.7%** → **语境约束真实贡献 +14.3 个百分点**
  - 两个数都来自留出集，**不是过拟合**
- 新增 5 条单测锁住该评测集（含"负例必须抽不出能力项""文本必须像真实 JD"）。

### 修真实数据暴露的过泛词误抽（新机制：语境约束）
- 实测发现：`engineering` 的「服务」在 465 条真实 JD 里是"服务质量/服务标准/服务团队"
  （物流运营语境）→ 精确率仅 **44.1%**；`adm_archive` 的「证照」多为"资质证件"
  → 精确率仅 **8.0%**。
- **修法不是删词**（删了会连带漏掉真需要的句子），而是新增 `CONTEXT_REQUIRED`：
  泛词只有在同行（或整篇文档）伴随**强语境词**时才算命中该能力项。
- 效果：engineering **44.1% → 92.7%**（误抽 935→58）、adm_archive **8.0% → 92.1%**
  （误抽 3,339→25），**召回几乎无损**，族识别完全不变（英文 93.6% / 中文 77.8%）。
- 语境词表**不能含该能力项自己的泛词**（否则等于没约束），有单测锁住。
- 语境表纳入 `sync_web_vocab.py` 自动同步 → 网页与 CLI **结构上不可能漂移**
  （同步后跨引擎回到 51/51 100% 一致）。

### 修一个真实 bug：标题判定误丢要求行
- `_looks_like_title` 用**有限动词表**做否定判断，遇到表外动词就一律误判成岗位名——
  真实 JD 里「具有较强的技术工程能力和技能」「吃苦耐劳，有良好的团队合作精神…」
  「与国内供应商建立并维护良好的合作关系」三条**被整段丢弃**。
- 改为**双向判据**：像岗位名 → 是标题；其余**默认不是标题**（宁可留，不可丢）。
  括号补充（"Java开发工程师（双休）"）也能正确识别。

### 走过的两条弯路（如实记录）
1. **直接换词**（把「服务」换成「微服务/服务化」）→ 中文族识别 77.8%→75.3%、
   评测集 1.0→0.967。真实 JD 表达太灵活（"业务场景""客服业务全流程"），换词就漏。
2. **语境词表里含自己的泛词** → 等于没约束（"业务"既在 domain 的泛词里、
   又在语境表里 → 永远通过）。已由单测锁住这条。

校验：110 单测全过（新增 13 条）、合成集 60 条 1.0、族识别 93.6% / 77.8%、
跨引擎 51/51 一致、audit 32/32、脱敏审计干净、词表同步

## [0.8.12] - 2026-10-26

### 真实回流报告上墙（脱敏样例）
- 新增 `docs/reflow_sample.md`：50 条真实中文 JD + 真实回流跑出来的**完整** markdown 报告
  （逐条明细表、方向对比、边界声明），不再只有汇总数字。
- 新增 `scripts/make_reflow_sample.py`：可复现的脱敏生成脚本。
  - 公司名 → 「企业 01 / 02 …」；回流备注 → 归因标签；岗位名保留；JD 原文不进报告。
  - **归因必须在脱敏之前算完**：先在原始备注上判定"可控/不可控"再压标签，
    否则标签措辞对不上原词，归因会变（「偏向学术」→「项目偏学术、缺落地」判不出来），
    **脱敏会悄悄改变分析结论**。`reflow.py` 新增预置归因支持（`_attr`）。
- 网页证据墙新增「真实回流报告长什么样」区块：4 个关键数字 + 分桶 offer 率条形图
  （条长=记录数、右侧=offer 率，直观呈现"最低分档 offer 率反而最高"）
  + 「r≈0 时先看分布再下结论」的解释 + 归因标签 + 完整报告链接。

### 修两个真实问题
- **网页渲染不幂等**：`renderRfSample` 用 `innerHTML=""` 清空，重复调用会叠加 DOM
  （DOM 桩实测 5 档变 11 行）。改为 `while(firstChild) removeChild()`，连调两次仍为 5 档。
- **脱敏方向分类器**：新代号格式改用「企业 01/02」纯序号（原来的「甲方 I1」可读性差）。

### 新增脱敏审计脚本（把"我们说脱敏了"变成可验证）
- `scripts/audit_anonymization.py`：检查所有公开文件里有没有可定位到具体投递的信息。
  「我们说数据脱敏了」是声明，别人没法验证——这个脚本把它变成**任何人都能跑的检查**。
- 判据设计（避免误报）：真正的泄露 = **公司名与该公司的岗位/结果同行同现**
  （能反查具体投递）。单独出现「用友」「金蝶」这类行业名词不算泄露；
  单独出现公司名出现在行业讨论里也不算。
- 自测 6/6：能抓到「公司+岗位同行」「原始备注」「个人信息」三类真泄露，
  且不误报行业名词与行业讨论——**一个只会说"通过"的检查脚本毫无价值**。
  自测已固化为 6 条单测。

校验：Node 实跑验证渲染（5 档、宽度与数值零偏差、与源数据一致、幂等）、
JS 语法过、6 个 section 标签平衡、单测 97 条全过、audit 32/32、
脱敏审计全部干净、脱敏报告可复现、词表同步。

## [0.8.11] - 2026-10-25

### 一条命令跑完整回流闭环（新增 `career-loop reflow`）
- 新增 `career_loop/reflow.py`：把「读记录 → 算预测分 → 校准 r → 漏斗归因 → 方向对比 → 出报告」
  抽成公共库，CLI、三个脚本共用同一套实现。
- 新增 CLI 命令 `career-loop reflow --records <投递记录> --profile <经历> --mode {early,terminal}`：
  CSV / JSONL / JSON 自动识别、列名自动嗅探、`--db-write` 可顺带写进 SQLite。
- **两种口径显式分开**：`terminal`（只有 offer 算正反馈，回答"能否预测录取"）与
  `early`（HR 有动作即算正反馈，回答"能否预测 HR 理不理我"）。混在一起会得出无法解释的中间值。
- **r 低时先看分布再下结论**：比较正/负反馈组的预测分中位数。分布重叠 → 结果本来就与岗位契合度无关；
  分布分得开但 r 不显著 → 样本量不够。作者 50 条真实中文 JD 上正是前者（14 vs 25 分，r = 0.003）。
- **没有 JD 原文的记录只进漏斗、不进相关系数**——不会拿编出来的分数充数。

### 修方向分类器：通用词抢位（真实数据暴露）
- 原分类器"先到先得"，导致「安全攻防研究员」含"研究"被归到金融/研究、
  「安全运营分析师」含"运营"被归到运营/增长；「电池研发测试」等硬件测试岗被笼统归到测试/质量。
- 改为**加权计分 + 命中位置**判定：专有词（攻防/投行/嵌入式…）3 分，通用词（研究/运营/分析…）1 分，
  同分时取岗位名里更靠前的词。18 条用例全过，分类更贴合岗位实质。

### 消除口径重复
- `scripts/calibrate_admission.py` / `analyze_funnel_attribution.py` / `run_calibration.py`
  改为调用统一库，删除各自复制的状态映射、归因关键词表与方向分类。
- 重构后逐条比对基线输出：**r、分桶、漏斗、归因计数全部零漂移**（方向分布因分类器修复而变化，属真实修正）。

### 新增示例与测试
- `examples/reflow_demo_records.csv` + `examples/reflow_demo_README.md`：
  示例数据**明确标注为编造**，并写明"示例 r 好看是因为编数据时按分数高低编的结果"，
  真实数据可能是 0 甚至负数。
- 新增 12 条单测锁住口径：状态映射、两种口径的正反馈集合差异、CSV/JSONL 嗅探、
  无 JD 记录不入相关系数、分布重叠诊断、报告必须写明口径与边界。

校验：91 单测全过、评测集 60 条一致率 1.0、audit 32/32、
英文族识别 93.6% / 中文族识别 77.8%、跨引擎 51/51 一致、词表同步。

## [0.8.10] - 2026-10-25

### 网页「中文抽取实验室」（新增，可交互）
- 证据墙新增「中文抽取实验室」：粘贴一段中文 JD → 实时显示逐项抽取结果，
  **左边黄色块是引擎没认出来的要求（custom 项）**，右边是词表已覆盖的能力项，
  底部给出未覆盖率与说明。附两条真实样本一键载入。
- 用的就是网页自己的 `parseJD`，所以显示的与「单 JD 匹配」区完全一致，不是另一套演示逻辑。

### 对齐网页 JS 与 Python 引擎（重要）
- 发现网页 JS 引擎缺 **中文内联切分** 与 **英文降噪**，与 Python 后端行为不一致
  （同一批中文 JD，网页抽出的能力项数明显偏少）。
- 补齐：`_split_inline_segments` 对应的 `splitInlineSegments`、英文分节标记、
  全大写标题 / URL / 招呼语 / 薪资行过滤（`isNoiseLine`）。
- 新增 `scripts/cross_engine_check.py`：把同一批真实中文 JD + 英文 JD 跑两边，
  逐条比对能力项集合 / 数量 / custom 数 / 每项权重。
  **当前结果：51/51 全部一致 ✓**（custom key 因两边哈希算法不同，按 quote 归一化后比对——
  它只是内部标识符，不影响任何用户可见结果）。

### 补词表漏掉的基础能力
- 「机器学习基础 / 机器学习 / 深度学习 / 神经网络」此前**完全不在词表**，
  而这是中文 AI 岗最普遍的门槛要求（实验室里被实测暴露出来）→ 补进 `llm_basics`。
- 配反向测试：「机器学习」只能属于 `llm_basics`，不许进别的族。

### 校验
79 个单测全过（新增跨引擎一致性与中文覆盖回归）、评测集 60 条一致率 1.0、
`audit.py` 32/32、英文族识别 93.6%、中文族识别 77.8%、跨引擎 51/51 一致、网页词表同步、JS 语法通过。

## [0.8.9] - 2026-10-25

### 网页「中文 vs 英文」对比模块
- 证据墙新增对比区：顶部并排显示两个公开数据集的族识别准确率（英文 93.6% / 中文 77.8%），下方列出中文 32 个族（n≥25）的分族表现，**弱族在前并用琥珀色标出**。
- 两栏解释差距来源：英文集只有 5 大类、边界清晰；中文市场 300+ 细分行业、同岗位天然跨族，且客服/助理类 JD 描述大半是福利模板。
- 附复现命令与「两个数据集均不入库」说明。
- 数据为脚本产出的静态快照（`scripts/real_eval_family.py` / `scripts/cn_eval_family.py`），第三方可自行下载复现；渲染逻辑做了幂等保护与宽度/数值一致性校验。

### 中文真实 JD 族识别检验（新增，公开可复现）
- 新增 `scripts/cn_eval_family.py` + `scripts/fetch_cn_eval_data.py`：基于公开数据集 HuggingFace `ngtranai09/china_job`（8,674 条真实中文招聘 JD）。
- **标签用岗位名而非数据集自带的 `searched_job_title`**：后者是采集时的搜索词，噪声极高（搜 "Program Development" 的 30 条里只有 1 条岗位名对得上），拿它当 ground truth 会得出错误结论。
- 只统计中文 JD（中文字符 ≥ 15%）、只统计岗位名可明确判族的记录 → 可检验样本 1,853 条。
- **中文族识别 72.2% → 77.8%**；英文公开集保持 93.6% 不变。

### 补中文词表（按"禁用过泛词"铁律）
- 补 service / project_mgmt / consulting / ai_solution / it_systems / media / banking / public_admin / film / product / education 等族的中文职能词。
- **「咨询」「顾问」被判定为过泛并剔除**：出现在 9.3% 的中文 JD 里（保险咨询 / 招聘咨询都算），换成「咨询顾问 / 管理咨询 / 咨询项目」等具体组合——准确率只掉 0.3 个点但词表干净得多。

### 两个被证伪的想法（已回滚，记录在案）
- **按词长加权提升判别力**：假设「3 字以上专有词更可靠、2 字通用词降权」，实测中文 top1 准确率反从 41.9% 掉到 40.5% → 长度不等于判别力，已回滚。
- **用 `searched_job_title` 当标签**：噪声太高，会得出完全错误的结论。

### 校验
75 个单测全过（新增 6 条中文词表回归）、评测集 60 条一致率 1.0、`audit.py` 32/32、英文族识别 93.6% 无回归、网页词表已同步。

## [0.8.8] - 2026-10-25

### 终局录取级校准（新增脚本）
- `scripts/calibrate_admission.py`：真实简历 × 真实中文 JD → 预测分，终局口径（只有 offer 算正反馈）算 Pearson r 与 20 分桶。
- 本批结论：**r = -0.016**（n=50），offer 率 14.0%，简历通过率 46.0%，面试→offer 转化 30.4%。
- `scripts/analyze_funnel_attribution.py`：简历关归因（**15/23 = 65% 属 HC/学历/地点等不可控因素**）+ 方向对比 + 面试淘汰短板逐条列出。每行标注「样本可信度」，n<3 的方向明确标为仅供参考。

### 修中文 JD 内联切分（真实数据暴露的召回缺陷）
- 根因：中文 JD 常把整份压在一行（"岗位职责：1、…；2、…任职要求：1、…"），`_split_sections` 只按换行切 → 整段当一行 → 只命中一个词（实测这类 JD 平均只抽 1 个能力项）。
- 新增 `_split_inline_segments` 按分号/句号/分节标题切出独立条目；50 条中文 JD 平均能力项 **4.40 → 6.36**。
- 顺带修两处 bug："有K8s项目优先"里的"优先"被误当 nice 段标题；"跟进线上问题排查"因动词不在标题表被当成岗位名丢掉。

### 补词与过泛词审计
- 按真实中文 JD 补 backend/frontend/qa/devops/embedded/ai_cv/ai_recsys/ai_data/operations/marketing/security 词，custom 垃圾项 32% → 20%。
- 审计剔除 5 个过泛英文短词（isp/tcp/poc/hdr/shell，均为子串误伤，shell 命中的是 "powershell"）。
- **记录一条方法论**：族识别准确率会奖励过泛词（中途虚涨到 94.8%，剔除后回到真实值 93.6%），必须同时看反向测试与误伤审计。

### 校验
69 个单测全过（新增 8 条中文回归）、评测集 60 条一致率 1.0、`audit.py` 32/32、族识别 93.6%（真实值）。

## [0.8.7] - 2026-10-25

### 引擎三项修复（真实数据暴露的真问题）
- **否定辖域判定**（`matching/match.py`）：原实现用固定短语表穷举否定词，「没搭建过工作流」「没独立负责过项目」「没写过正式文档」这类「否定词+动作词」组合漏判成 full（实测 3/8 误判）。改为按中文否定辖域判定：否定词 + 填充词白名单 + 转折词切断 + 子句边界；另加「只/仅/光」限定词判定。评测集 50→60 条，一致率仍 1.0。
- **英文 JD 降噪**（`matching/extract.py`）：加英文分节标记、URL / 全大写标题 / 招呼语 / 薪资行过滤。custom 垃圾项占抽取总数从 **29.5% → 0%**，平均能力项 17.1 → 12.08/JD，缺口清单不再列「ESSENTIAL DUTIES」这类模板标题。
- **sales 族判别词**（`matching/schema.py`）：从公开数据集 SALES 类 `clean_skills` 统计出高判别力词（relationship building / lead generation / account management / b2b sales…）。族识别 **91.9% → 93.6%**，SALES **69.8% → 78.4%**，其余四族不变，每组新词配反向测试。

### 闭环校准搬进浏览器（`docs/index.html`）
- 新增「用你自己的结果校准」区块：记录每次投递的匹配分与真实结果（localStorage，不上传），实时算出 **Pearson r + 20 分桶正反馈率 + 结论**。
- 数学口径与 `career_loop/calibrate.py` **完全一致**（已用同一份数据交叉验证：r = −0.06453413… 两边同值）。
- 支持导出 CSV；示例数据明确标注为「编造的，仅用于看界面效果」。

### 校验
- 61 个单测全过（新增 14 条回归测试）、评测集 60 条一致率 1.0、`audit.py` 32/32、网页词表已同步。

## [0.8.6] - 2026-10-25

### 评测体系升级（W6）
- 控制回归集 `data/eval_sample.jsonl` 从 42 条扩到 **50 条**：新增 `GENERAL_DIMS` 通用能力覆盖（writing、exec_project）+ 8 条边界/覆盖样本；规则基线一致率仍 1.0。
- 正式把公开 HF 集的真实端到端验证（族识别 91.9% / r=0.193）列为评测体系第二支柱（`docs/benchmark.md` §2.2）。
- 修正口径：不再把合成控制集夸大为「真实人工标注」；如实记录引擎已知局限（否定语境动作词消解弱），并列为后续修复项。
- 同步更新 benchmark.md / methodology.md / README / submission.md / evidence.md。

## [0.8.5] - 2026-10-25

### 社媒传播素材（W8 复盘长文）
- 新增 `docs/retro.md`：项目复盘长文（约 2000 字），含「被真实数据打脸」叙事、诚实边界、数据教我的真实求职建议；全文脱敏（只出聚合数字，无简历/公司名）。
- `docs/share-kit.md` 新增「复盘长文发布」章节（分渠道建议 + 钩子 + 诚信底线）。
- `README.md` 接入 retro.md 链接、W8 标记完成。

## [0.8.4] - 2026-10-25

### 网页 demo 升级为「工具」（投稿功能扩展）
- 新增「批量岗位排序」：粘贴多个 JD（用单独一行的 `---` 分隔），按匹配分排序并附最划算补强 —— 把 CLI 的 `recommend` 搬上网页。
- 新增「全行业适配」：用简历关键词覆盖 65 个岗位族的能力项，给出行业覆盖度 Top16 + 主要缺口 —— 把 `scan` 思路搬上网页。
- 新增「导出 Markdown 报告」：一键下载当前排序/适配/单岗位结果。
- 纯前端实现，复用 `compute()` / `DOMAIN_PACKS` / `ALL_DIMS`，零后端、零新依赖。
- 更新 README 路线图（W4/W5/W7 进度）、版本对齐 0.8.4。

## [0.8.3] - 2026-10-25

### Added (证据墙：把「可证伪」变成看得见的证据)
- **`docs/evidence.md` 证据墙**：公开数据集族识别 **91.9%**、引擎分↔真实标注 **r=0.193**、
  三步闭环（apply → log → calibrate），并**主动公开**作者私有 40 条投递 **r=-0.255** 的失效区间
  （只公开聚合统计，不含个人信息 / 公司名 / JD 原文）。
- **`scripts/real_eval_scatter.py`**：用公开 2,000 对真实 (简历, JD) 重画校准散点图
  `docs/evidence-scatter.png`（深色主题、趋势线、r 标注），可第三方复现。
- **网页新增「验证闭环 · 证据墙」区块**：三个关键数字卡 + 真实散点图 + 三步闭环，
  并在导航加入「证据墙」锚点；hero 统计新增「91.9% 真实 JD 族识别」。
- README / `docs/submission.md` / `docs/share-kit.md` 均加入证据墙入口与配图建议。

## [0.8.2] - 2026-10-25

### Added (1024 造物挑战投稿就绪)
- **社媒分享富预览**：`docs/index.html` 增加 OG / Twitter 标签，并生成 1200×630 封面
  `docs/og-cover.png`，分享链接可出卡片（直接服务评审「社媒分享 +30」）。
- **页面底部「复制本页链接」按钮**，方便随手带话题分享。
- **离线一键演示** `scripts/demo_cli.py`：免 API Key、不落库，演示「单 JD 匹配 → 多 JD 排序 →
  补强性价比」全流程，供评委 / 用户一键看核心能力。
- **投稿包** `docs/submission.md`（抄填投稿表单 + 与四项评审标准逐条对应）与 **社媒分享 Kit**
  `docs/share-kit.md`（各平台现成文案、必带话题、素材清单、冲人气分方法）。
- 修：网页 hero / 统计里的「岗位族」数字由陈旧值 33 更正为引擎真实值 **65**（引擎与 README 一致）。

### Fixed
- 清理仓库根目录测试残留的空杂物文件。

## [0.8.1] - 2026-10-24

### Added
- **English capability aliases (`EN_VOCAB`)**: career-loop can now read English JDs
  and résumés, not just Chinese. Scoped to the 5 categories covered by the public
  evaluation dataset + general dimensions; other families' English support is
  "to-be-added" and not overclaimed.
- **Real-data validation** (`docs/real_eval_report.md`, `scripts/real_eval_family.py`,
  `scripts/real_eval_calibrate.py`): replaced the hand-written eval set and the
  synthetic 29-row calibration demo with public datasets (job-resume-matching:
  1,167 real JDs + 9,544 résumés + 122,560 real match labels). Family-identification
  accuracy **91.9%** on real JDs; engine score vs. real `final_score` Pearson **r = 0.193**
  (2,000 real pairs, weak positive — honest vs. the old synthetic r = 0.694).
- **`scripts/fetch_real_eval_data.py`**: one-command downloader for the public
  evaluation dataset (saved as `data/real_eval/job_resume_*.csv`). The dataset is
  large (~250MB) and is **gitignored** so the repo stays lean; third parties
  reproduce the validation by running this script.

### Changed
- `detect_domains` AI judgment now uses a hardcore `AI_CORE_KW` list instead of all
  TAXONOMY keywords, fixing a real cross-family bug where generic business words
  (`business process` / `kpi` / `sql`) mis-tagged non-AI JDs as AI.
- Removed over-broad short tokens (`ui`, `ux`, `ps`, `vi`) from the design family and
  added real sales-title words (`sales representative`, `account executive`, …),
  discovered via the real-data test (SALES accuracy 0.58 -> 0.70).

## [0.8.0] - 2026-10-24

### Added
- **65 job families / 166 family-level capabilities** (was 33 / 52): the v0.7
  families were mostly single-dimension stubs. Added `backend`, `frontend`, `qa`,
  `devops`, `security`, `embedded`, `electrical`, `mechanical`, `quality`,
  `banking`, `insurance`, `securities`, `consulting`, `media`, `film`, `game`,
  `translation`, `service`, `retail`, `catering`, `domestic`, `transport_ops`,
  `energy`, `automotive`, `agriculture`, `research`, `public_admin`, `social`,
  `psychology`, `sports`, `logistics`, `tourism_cn`; and deepened the existing
  thin families (e.g. `legal` 1->4, `supply` 1->3, `education` 2->4).
- **`career_loop/matching/taxonomy_cn.py`**: heuristic mapping from the 8 top-level
  classes of China's Occupation Classification Dictionary to career-loop job
  families, plus a coverage matrix so "how much do we cover" can be audited
  against an external skeleton. Explicitly labeled heuristic, not official data.
- **`scripts/sync_web_vocab.py`**: regenerates the JS vocabulary inside
  `docs/index.html` from the Python schema; `--check` mode catches drift in CI.
- Coverage check grew from 30 to **75 probe roles** in 8 groups, including a
  deliberate *long-tail* group (tea artisan, wedding planner, drone pilot, flight
  attendant, courier, bartender, pet groomer, nail artist, LARP host) that has no
  built-in family, so fallback rate is measured honestly.
- `scripts/coverage.py --mode rule|llm|both`, `--only <group>`, `--quiet`.

### Fixed
- `scripts/coverage.py` compared quotes without stripping list markers, so LLM
  mode (which drops the `1.` prefix) scored a false 13% recall on long-tail
  roles. Now both sides are normalized; LLM long-tail recall is 97%.

### Fixed
- `_claim_lines` kept only the top-4 capabilities per line. With 189 dimensions a
  single line can hit a dozen, so two-character keywords (业务 / 沟通 / 会计 /
  招聘 — most Chinese capability words are two characters) were crowded out, and
  ties between equal-length hits were broken by the alphabetical order of the
  key name, i.e. arbitrarily. Now: hits with a >=3-character keyword are all
  kept, 2-character hits are capped at 4 per line.
- Generic words that were wrongly routing JDs into a family and inventing gaps:
  `domain` lost bare 岗位 (every JD says it); `rs_paper` now needs 学术论文 /
  发表论文 / 文献检索 rather than bare 论文 (a PM JD means *reading* papers);
  `csl_industry` lost 竞品分析 (a product/marketing action, not consulting);
  `csl_delivery` lost 方案设计; `devops_monitor` now needs 监控告警 / 监控体系
  rather than bare 监控 (a PM JD monitors *effect*); `tr_written` lost bare 翻译
  ("translate business problems into Agent solutions" is not translation work);
  `pub_document` lost bare 政策 (税务政策 is not civil-service writing);
  `pub_service` lost bare 办事; `rs_exp` lost bare 基金; `rs_method` lost bare
  计量; `psy_counsel` lost 访谈 (user interviews are a PM action).
  Each has a paired test asserting the real role still detects it, so tightening
  a word cannot silently break the family it belongs to.

### Changed
- 47 unit tests (was 36), 32 CLI checks, eval consistency 1.0 — all still green.
- Shipped browser samples still score 58.3 / 53.6 / 81.8, identical in Python
  and JS.
- Author / repository metadata now points to `github.com/jian935/career-loop`.

## [0.7.0] - 2026-10-24

### Added
- **`scan`**: resume × a job corpus -> all-industry ranking, industry fit,
  gap ranking, and next actions.
- Seniority detection (`intern/junior/mid/senior/exec`) with level-aware
  down-weighting; a separate "goal direction" section (e.g. `--goal ai`).
- `--no-llm` (and `CAREER_LOOP_NO_LLM=1`) to force rules; the CLI audit now runs
  fully offline.
- Real-corpus scripts: `scripts/fetch_real_jds.py` (Remotive + Jobicy, public
  feeds), `scripts/fetch_target_jds.py` (Himalayas, product/AI entry-mid pool),
  and `scripts/coverage_real.py`.
- `level_hint` from the source (e.g. Himalayas `seniority`) is honored by
  `detect_level` before falling back to title/description regexes.

### Fixed
- Seniority detection matched `intern` inside `internal`; now word-boundary.

### Changed
- 36 unit tests, 32 CLI checks.

## [0.6.0] - 2026-10-24

### Added
- **LLM extraction is no longer bounded by the built-in vocabulary.** It accepts
  `custom:<slug>` keys and normalizes invented keys to `llm:<slug>`, so a role with
  no job-family pack (e.g. 茶艺师) gets structured capability items instead of
  line fragments. In a tea-artisan test the rule baseline scored 45.5% with
  fragment labels; the LLM produced five clean items and 83.3%.
- `--llm` coverage is now meaningful for jobs outside the 33 packs.

### Changed
- 32 unit tests.

## [0.5.1] - 2026-10-24

### Added
- The CLI now actually uses the LLM mode (`match` / `whatif` / `apply` /
  `recommend` / `add-jd`); it was implemented but never wired.
- LLM response cache at `~/.career_loop/llm_cache` (hash of model + prompt),
  disable with `CAREER_LOOP_NO_CACHE=1`.
- `doctor` command: Python / DB / LLM / cache / eval-set status.

### Fixed
- Configuring an API key had no effect; every command silently used rules.

### Changed
- 30 unit tests, 31 end-to-end CLI checks.

## [0.5.0] - 2026-10-24

### Added
- `intern` command: 10 built-in internship directions, ranked by
  (goal match, weighted score), plus a cohort timeline
  (daily internship -> summer -> autumn recruiting -> spring).
- Browser demo: an internship direction panel that updates with the profile.
- `--presets` to use your own internship JSONL.

### Fixed
- A JD's first line (job title without `#`) was parsed as a requirement,
  producing noise like "补：产品经理实习生".

### Changed
- 28 unit tests, 30 end-to-end CLI checks.

## [0.4.0] - 2026-10-24

### Added
- **Works for any role**, not just AI/tech: a layered vocabulary (AI/tech +
  9 universal capabilities + 12 job families) and a **custom fallback** that keeps
  requirements no vocabulary matched instead of silently dropping them.
- `whatif` command: counterfactual uplift — how much the score rises if one
  requirement is brought to "full".
- Browser demo (`docs/index.html`): zero-install, local-only, same rule engine as
  Python; deep link `?s=2` opens the finance sample.
- Docs: `docs/architecture.md`, `docs/methodology.md`, `docs/benchmark.md`.
- Governance: `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT`, `LEGAL_DISCLAIMER`.
- CI workflow (Linux + Windows, Python 3.10-3.13) and `scripts/audit.py`.
- Dockerfile for a one-command run.

### Fixed
- `apply` / `log` did not forward `--db`, so they could read/write the default
  database instead of the one you passed.
- `collect` returned success on a non-existent directory.
- `_claim_lines` used a top-1 rule that let a long job-family keyword suppress a
  shorter core keyword (e.g. `资产负债表` hid `会计` / `金蝶`).
- Packaging missed `career_loop.matching` (editable installs worked, wheels would
  not).

### Changed
- Claim rule now keeps the top 4 lexical hits per line.
- `score`/`gaps` unchanged; eval baseline remains 1.0.

## [0.3.0] - 2026-10-24

### Added
- `collect`: batch-import raw JDs from a folder, strip job-board noise, dedupe.
- `demand`: capability demand heat map across a JD pool, with per-capability
  coverage and a build-priority score.

## [0.2.0] - 2026-10-24

### Added
- `recommend`: rank a JD pool for a given profile, and estimate which capability
  unlocks the most roles.

## [0.1.0] - 2026-10-24

### Added
- Initial closed loop: matching engine, weighted score, gap ranking with verbatim
  evidence, labeled eval set (42 cases), Pearson calibration with buckets, SQLite
  storage, CLI, optional Streamlit dashboard.
