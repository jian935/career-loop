# 回流分析示例数据（**编造**，仅用于演示命令怎么跑）

> ⚠️ **这份 CSV 里的公司名、岗位、结果、备注全部是编造的。**
> 它存在的唯一目的：让任何人（包括评委）能一条命令跑通 `career-loop reflow`，
> 看到报告长什么样、r 怎么算、漏斗怎么归因。
>
> **不要**把它当成真实求职记录引用或对外宣称。

> 🔍 **一个必须说清的事**：这份示例数据跑出来的 **r ≈ 0.46（看着还挺漂亮）**，
> 但那是**因为编数据的时候我是按"分数高的确实拿到 offer"来编的**。
> 换成你自己真实回流的数据，r 完全可能是 0 甚至负数——
> 本仓库用真实中文 JD 那 50 条跑出来的是 **r = 0.003**。
>
> 这正是这个工具存在的意义：**它不会因为数据好看就给你好结论。**
> 所以示例数据只用来演示"命令怎么跑"，任何结论都必须用你自己的真实记录重算。

## 用法

```bash
# 用你自己的经历文件替换下面的 profile
python -m career_loop reflow \
  --records examples/reflow_demo_records.csv \
  --profile examples/profile_me.md \
  --mode terminal \
  --out /tmp/reflow_demo.md
```

- `--mode terminal`：终局口径，只有拿到 offer 才算正反馈（默认）
- `--mode early`：早期口径，HR 有沟通/感兴趣/面试邀约就算正反馈

## 换成你自己的数据

CSV 需要这几列（列名可以不同，`reflow` 会自动嗅探）：

| 列名（任选其一） | 必需 | 说明 |
|---|---|---|
| `id` / `投递ID` / `idx` | 否 | 记录编号 |
| `company` / `公司名称` | 否 | 公司 |
| `role` / `岗位名称` / `title` | 否 | 岗位名（用于方向归类） |
| `jd_text` / `JD原文` / `job_description` | **是**（要算 r 就必需） | JD 原文。**没有它就进不了相关系数计算**，只能进漏斗统计 |
| `outcome` / `status` / `终局结果` / `状态` | **是** | 结果或平台状态文本 |
| `note` / `回流备注` / `备注` | 否 | 结果备注，用于归因"可控 vs 不可控" |

也支持 JSONL（每行一个对象）和 JSON 数组。

## 结果放哪

```bash
# 顺带写进 SQLite，这样 status / calibrate 命令也能用上
python -m career_loop reflow ... --db-write --profile-name "你的名字"
python -m career_loop status
```

**你的记录始终留在本地**：SQLite 默认在 `~/.career_loop/loop.db`，不进仓库、不联网。
