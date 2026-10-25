# GitHub 仓库页配置清单

> 这份清单里的每一项都可以直接粘进 GitHub 仓库设置页。写在这里是因为
> **仓库设置不能写进代码、也不该写进代码**——它是账号侧的一次性配置。
>
> 依据：README 是仓库的"门面"，但**仓库页的 description / Topics 决定别人能不能搜到你**——
> GitHub 搜索结果页只显示 Topics 命中项，description 出现在搜索结果摘要里。

---

## 1. 仓库 Description（Settings → General → Description）

上限 350 字符。推荐这一条：

```
Job-fit scoring you can falsify: JD × experience → weighted score + gap list + counterfactual, then calibrate against real outcomes. 66 job families, zero-dependency Python core, browser demo, reproducible evals.
```

备选（更强调"可证伪"这个差异点）：

```
A job matcher that admits when it's wrong: match score + gap list + counterfactual, then calibrate r against your real application outcomes. Open source, MIT, zero-dependency core.
```

> 关键词覆盖：job-match / resume / career / calibrate / falsify / open-source / python。
> 搜 "resume matcher" 的人能搜到，搜 "job fit score" 的人也能搜到。

---

## 2. Topics（仓库页右侧 "About" → Topics，点齿轮编辑）

最多 20 个。推荐这 12 个（覆盖三类搜索意图）：

```
job-match
job-search
resume-matcher
career
job-fit
self-assessment
evaluation
calibration
counterfactual
python
local-first
open-source
```

> **加不加 `llm` / `ai`？** 建议 **加 `llm`**，但**不要**堆 `ai` / `machine-learning` ——
> 这两个词竞争极大、你的项目也不是以模型能力取胜。`llm` 能吸到"我想让我的匹配更准"的搜索流量。
>
> **`falsifiability` 要不要加？** 建议加，它是这个项目最独特的标签，搜索量小但**精准**——
> 搜这个词的人多半就是想找"诚实的评估工具"。可以放第 13 位：
> `falsifiability`

---

## 3. 社交预览图（Settings → General → Social preview）

上传 `docs/og-cover.png`（1200×630，已按 GitHub 预览比例做）。

检查点：
- 打开链接分享到微信 / X / Slack 时出的卡片是否带图（带图的链接点击率显著更高）
- 图上的大字是"66 岗位族 / Pearson r 可校准 / 0 依赖"——如果之后改了词表数字，记得同步重画

---

## 4. 仓库页功能开关（Settings → General → Features）

| 功能 | 建议 | 理由 |
|---|---|---|
| Issues | ✅ 开 | 已配 bug_report.yml / feature_request.yml 模板 |
| Discussions | ✅ 开 | "这个岗位族识别不准"这类讨论比 issue 更合适，也是 star 的常见触发点 |
| Projects | ❌ 关 | 本项目用 roadmap 段 + CHANGELOG 就够了 |
| Wiki | ❌ 关 | 文档已经在 `docs/` 里，wiki 会变成第二份不同步的真相 |
| Sponsorship | ❌ 关 | 还没到那一步 |

---

## 5. 分支保护（Settings → Branches → Branch protection rules）

对 `main` 加一条规则：
- Require a pull request before merging → **开**
- Require status checks to pass → **开**，必选检查填 `Unit tests` / `CLI audit`
  （CI 里的 job 名就是 `test` 和 `audit`）

> 这条规则本身就是信号：**一个连自己分支都保护不了的仓库，很难让人相信它的评测数字。**

---

## 6. 关于页（About 区域的一句话）

```
career-loop turns "should I apply?" into a falsifiable question:
score → gap list → apply → log the real outcome → calibrate r → fix the weights.
```

---

## 7. 发布后 48 小时内要做的三件事

1. **去 `docs/index.html` 打开一次线上地址**，确认：图片加载正常、粘贴 JD 能出分、
   证据墙区块能展开、**手机宽度下不横向溢出**。
2. **看一遍 Actions**：第一次 push 触发的 CI 应该是绿的（本地已模拟过全新克隆的五步全绿）。
3. **确认 Pages 已生效**：Settings → Pages 应显示 "Your site is live at
   https://jian935.github.io/career-loop/"。

---

## 8. 拿到第一个 star 之后

star 的转化通常来自三处，按性价比排序：

1. **README 首屏**——第一屏必须让人明白"这东西和别的匹配器有什么不一样"。
   本项目的差异点是"可证伪"，首屏已经直接写了。
2. **配图**——`docs/demo.png` + 演示视频已经在首屏。视频建议在社交平台
   带 #1024造物挑战 话题发布（见 `docs/share-kit.md`）。
3. **评论区/Issues 区**——对每一个"某个族识别不准"的 issue 认真回复并贴上
   `docs/evidence.md` 的对应章节。**这个项目最吸引人的恰恰是它愿意公开自己的失败**，
   回复时把失败也写进去。
