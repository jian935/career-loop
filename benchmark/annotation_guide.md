# Annotation guide

The goal is to label, for each requirement, what the **profile** actually shows.
You are not judging whether the person is a good candidate.

## Decision rule

Ask one question: **does the profile contain a concrete instance of doing this?**

| Status | Use when | Example |
| --- | --- | --- |
| `full` | There is a specific project, output, or number that proves it. | "用 Flask 写了后端，Docker 部署，最高在线 200 人" |
| `partial` | It is mentioned, but with weak, hedged, or indirect evidence. | "了解 LangChain，搭过 demo，但没上线" |
| `missing` | Not mentioned at all, or explicitly denied. | "没用过任何 AI 编程工具" |

### Tie-breakers

1. **A course or a certificate is `partial`, not `full`.** It shows exposure, not
   delivery, unless the JD explicitly accepts coursework.
2. **"参与" without a concrete contribution is `partial`.**
3. **Numbers and shipped artifacts push toward `full`.**
4. **Explicit negation is `missing`**, even if the topic is mentioned.
   (`没用过` / `没做过` / `完全没有`.)
5. **Do not infer.** If the profile says "写了 Python" but the requirement is
   "用 Python 做过数据分析", that is at most `partial`.
6. **Evidence must be verbatim.** Copy the shortest span that supports the label.

## Worked examples

**Requirement:** 熟悉 RAG / 检索增强
- Profile: "用 LangChain 搭了简单的检索问答，但没有做向量检索，是按标题切块关键词匹配"
  → `partial` (did retrieval, but not RAG in the usual sense; explicit gap)

**Requirement:** 能独立完成纳税申报
- Profile: "做过代理记账实习，用金蝶做凭证录入和纳税申报"
  → `full` (did it, tool named)

**Requirement:** 有中级会计职称
- Profile: "会计学本科，做过代理记账实习"
  → `missing` (no certificate)

**Requirement:** 具备跨团队沟通协作能力
- Profile: "跟设计和研发一起推了两个活动上线"
  → `full` (cross-team, shipped)

## Multi-annotator protocol

- Double-label at least 20% of cases (minimum 20 cases).
- Do not discuss individual cases before submitting.
- After both submit, run `agreement.py`. Target **Cohen's kappa >= 0.70** per
  capability.
- Adjudicate disagreements in a third pass; record the final label and keep both
  raw annotations.
- If a capability's kappa is below 0.70, rewrite the rule for that capability
  before labeling more.

## What not to do

- Do not change the requirement text to make it easier to match.
- Do not mark `full` because the candidate "seems strong".
- Do not paste the whole profile as evidence; quote the supporting span only.
- Do not include names, phone numbers, emails, or employer names in evidence.
