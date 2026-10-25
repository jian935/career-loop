# 真实数据检验报告（Real-data Validation）

> 目的：把 career-loop 的「覆盖面」和「匹配分是否可信」两项声明，从「手写样例 + 合成 demo」
> 替换为**公开、可复现、可第三方验证**的真实数据检验。
> 生成日期：2026-10-24

## 1. 数据来源（全部公开、合规）

| 数据集 | 内容 | 规模 | 许可 |
|---|---|---|---|
| HuggingFace `nonameee12233/job-resume-matching`（`job.csv`） | 真实岗位 JD，含 `category` 标注 | 1,167 条 | CC BY 类 |
| 同上 `cv.csv` | 真实简历（含 `resume_text`） | 9,544 份 | 同上 |
| 同上 `matches.csv` | 候选×岗位真实匹配标注（`final_score` / `label_strength`） | 122,560 对 | 同上 |

数据存于 `data/real_eval/`，仅保留公开来源引用，不含任何 PII。JD 文本来自公开招聘渠道
（Indeed 等），按数据集许可使用。这些数据集带 CC BY 等许可，注明来源即可合规复用。

## 2. 族识别准确率检验（1,167 条真实 JD）

**方法**：每条真实 JD 的公开 `category`（FINANCE / HR / SALES / BUSINESS-DEVELOPMENT /
INFORMATION-TECHNOLOGY）作为 ground truth；用 `detect_domains()` 预测岗位族，检查预测是否落在
「该类别对应的 career-loop 岗位族集合」内。

**结果**：

| 真实类别 | 准确率 | n |
|---|---|---|
| FINANCE | 96.6% | 236 |
| HR | 99.5% | 220 |
| BUSINESS-DEVELOPMENT | 100% | 239 |
| INFORMATION-TECHNOLOGY | 93.3% | 240 |
| SALES | 78.4% | 232 |
| **总体** | **93.6%** | **1,167** |

**检验驱动的真实修复**（这些 bug 用合成数据永远发现不了）：
1. AI 判定被通用业务词（`business process` / `kpi` / `sql`）触发 → 大量非 AI 岗位误判为 `ai`。
   改为只用硬核 AI 词判定（`AI_CORE_KW`）。
2. design 族的 `ui` / `ux`、`ps` / `vi` 等过短词在英文里无处不在 → 大量跨族误判。已移除。
3. sales 族未覆盖真实销售职位标题词（`sales representative` / `account executive`）→ 已补。

SALES 曾是最大短板（69.8%）：根因是通用软技能英文词（`performance management` / `training` 等）会跨族命中 hr。
v0.8.7 用公开数据集的 `clean_skills` 统计补了高判别力销售词（relationship building / lead generation / account management / b2b sales…），提到 78.4%，其余四族不变；
属于已知局限，列入待修（下一步：英文短词系统性治理）。

## 3. 匹配分校准检验（2,000 真实配对）

**方法**：从 122,560 对真实标注里抽样 2,000 对，用引擎对 (简历, JD) 算匹配分，
对照数据集自带的 `final_score`（真实匹配度标注），算 Pearson 相关系数 r。

**结果**：
- **Pearson r = 0.193**（200 对 0.154，2,000 对 0.193，稳定弱正相关）
- 引擎匹配分均值 17.1；真实 `final_score` 均值 0.586（范围 0.44–0.71，被数据集压缩在窄区间）

**解读**：
- 这是**真实算出的 r**，取代了原来 29 条手写 demo 的 `r = 0.694`（后者按「分高就成功」编造，属自证）。
- r 偏低且为正，符合预期：引擎当前是**规则关键词覆盖率**基线，而 `final_score` 是**多维语义匹配**
  （语义相似度 + 技能 + 类别 + 经历 + 教育）。两者方向一致（r > 0）但解释力有限。
- 含义：当前匹配分适合做「岗位内能力缺口清单 / 投递优先级粗排」，还**不能**当作精确的录取预测。
  这正是 README 反复强调的诚实边界。

## 4. 诚实边界（发布前必须保留）

1. 真实数据均为**英文**公开数据集。引擎中文路径（65 族主战场）的检验，依赖**用户真实回流的中文 JD**。
2. 英文支持目前仅覆盖 5 大类对应族 + 通用维度；其余岗位族英文识别为「待补」。
3. `final_score` 是算法标注，**非真人投递结果**。校准的终极目标仍是用户真实回流
   （`apply` + `log` + `calibrate`，详见 README 的校准闭环）。
4. 中文 JD 的「覆盖面 / 准确率」声明，目前仍以内部检验集（75 岗位）为主，真实英文数据作为补充佐证。

## 5. 复现

```bash
# 1) 拉取公开数据集（约 250MB，来自 HuggingFace nonameee12233/job-resume-matching）
python scripts/fetch_real_eval_data.py

# 2) 复现两项检验
python scripts/real_eval_family.py                      # 族识别准确率（1,167 真实 JD）
python scripts/real_eval_calibrate.py --n 2000 --seed 7  # 真实 r（2,000 配对）
```

- 数据集**不入库**：`data/real_eval/` 已在 `.gitignore` 中排除，第三方用上面的脚本自行下载即可。
- 若网络无法访问 HuggingFace，可手动从数据集页面下载 `job.csv` / `cv.csv` / `matches.csv`
  并分别重命名为 `job_resume_job.csv` / `job_resume_cv.csv` / `job_resume_matches.csv`，
  放到 `data/real_eval/` 下。
- 本报告所有数字均来自上述公开数据的确定性抽样（seed=7），可第三方复现。
