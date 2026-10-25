# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

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
- Author / repository metadata now points to `github.com/jian35/career-loop`.

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
