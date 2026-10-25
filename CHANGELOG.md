# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

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
