# strict-agent-loop

[English README](./README.md) | 简体中文

`strict-agent-loop` 是一个给 Codex 用的 skill，目标是把“容易偷懒、容易跳步骤、容易把中间过程压缩掉”的任务，强制变成严格的小步循环。它要求每一轮只做一个小任务、做完必须验证、验证后必须落盘，然后再判断是否继续。

仓库里的辅助脚本只依赖 Python 标准库，并按兼容 Python `3.7` 到 `3.14` 的方式编写。

## 这个 skill 解决什么问题

- Codex 做长任务时容易把中间过程压缩成一句话。
- 你希望每一轮都只能做一个边界明确的小任务。
- 你希望关键信息必须写入文件，而不是只靠模型记忆。
- 你希望在无人值守场景下，外层循环可以跨越多个 Codex 调用持续运行。
- 你希望进度播报能明确体现“它还活着”，而不是看起来像卡死。

## 它怎么工作

它支持两种模式：

- `interactive`：当前 Codex 会话就是控制器，直接对用户播报每一轮。
- `unattended`：由 `scripts/supervise.py` 持有外层 while 循环，反复调用 `codex exec` 或 `codex exec resume`。

两种模式下，内层控制器都遵守同一套协议：

1. 从 `.codex-loop/state.json` 读取权威状态。
2. 宣布下一轮要做的那个原子任务。
3. 执行这一轮，并做验证。
4. 把这一轮的事实写入磁盘。
5. 重跑机器可检查的停止条件。
6. 刷新进度播报和各类追加式日志。
7. 满足停止条件就停，否则继续下一轮。

这里特意把“当前状态”和“全量轨迹”分开：

- `state.json` 保存当前状态和最近一段历史窗口。
- `iterations.jsonl`、`events.jsonl`、`status-history.jsonl`、`rounds/` 保存全量追加式记录。

这样即使为了节省上下文去压缩 `state.json` 的历史窗口，全周期轨迹也不会丢。

## 持久化产物

下面这些文件就是这套机制的核心。它们的设计目标是：就算会话断了、上下文压缩了、控制器换人了，信息也仍然可查。

- `.codex-loop/state.json`：当前权威状态、限制条件、下一步任务、滚动历史窗口。
- `.codex-loop/events.jsonl`：控制面事件时间线，包含每轮开工播报。
- `.codex-loop/iterations.jsonl`：每一轮已验证事实的追加式账本。
- `.codex-loop/status-history.jsonl`：每次状态播报和 heartbeat 的追加式快照。
- `.codex-loop/latest-status.txt`：最新的人类可读状态。
- `.codex-loop/latest-stop-report.json`：最新一次机器停止条件评估结果。
- `.codex-loop/run-summary.md`：当前整个周期的汇总。
- `.codex-loop/rounds/iteration-XXXX.md`：每一轮的人类可读摘要。
- `.codex-loop/supervisor/`：仅无人值守模式使用，保存外层监督器的 prompt、Codex JSONL 输出和调用日志。

## 安装方式

### 方式一：安装到 Codex skills 目录

```bash
git clone https://github.com/HansBug/strict-agent-loop "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
```

之后就可以直接通过 `$strict-agent-loop` 调用。

### 方式二：放在任意路径，通过显式路径调用

```bash
git clone https://github.com/HansBug/strict-agent-loop /path/to/strict-agent-loop
```

调用时显式写出路径：

```text
请使用位于 /path/to/strict-agent-loop 的 $strict-agent-loop 来处理这个任务。
```

## 交互模式快速开始

先在目标仓库里初始化状态：

```bash
python /path/to/strict-agent-loop/scripts/init_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --goal "以严格原子步骤安全修复 parser。" \
  --global-stop-condition "只有当 pytest 通过、回归测试存在且 parser 缺陷被修复时才允许停止。" \
  --workspace-root /abs/path/to/repo \
  --success-evidence "pytest -q passes" \
  --next-task "先用一个最小回合复现 parser 的失败行为，并把失败事实固定下来。" \
  --stop-command "pytest -q" \
  --require-path tests/test_parser_regression.py
```

然后明确告诉 Codex：

```text
请使用 $strict-agent-loop 来处理这个仓库。
开始前先读取 /abs/path/to/repo/.codex-loop/state.json。
本次使用 interactive 模式。
每一轮开始前，必须先告诉我：
- 当前是第几轮
- 之前已经完成了多少轮已验证任务
- 这一轮唯一要做的原子任务是什么
- 这一轮的完成条件是什么
- 全局停止条件是什么
- 满足什么条件这一轮之后就可以停止
- 如果已经有数据，就顺便告诉我最近几轮平均耗时和大致 ETA
然后把同样的信息写入 .codex-loop/events.jsonl。
每一轮完成后，必须先验证，再运行 check_stop.py，然后运行 report_status.py。
不允许擅自扩大范围，也不允许提前宣称完成。
```

## 无人值守模式快速开始

先初始化为无人值守模式：

```bash
python /path/to/strict-agent-loop/scripts/init_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --goal "在不偷懒的前提下，以严格原子步骤完成排队中的任务。" \
  --global-stop-condition "只有当 verify_task.py 返回 0 且最终报告文件存在时才允许停止。" \
  --workspace-root /abs/path/to/repo \
  --operating-mode unattended \
  --success-evidence "python verify_task.py returns 0" \
  --next-task "从当前仓库状态出发，先做一个最小且可验证的推进步骤。" \
  --stop-command "python verify_task.py" \
  --require-path output/final-report.md \
  --max-iterations 200 \
  --supervisor-max-rounds-per-invocation 5 \
  --supervisor-max-consecutive-failures 3
```

再启动监督器：

```bash
python /path/to/strict-agent-loop/scripts/supervise.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --skill-path /path/to/strict-agent-loop \
  --heartbeat-seconds 30 \
  --max-invocation-seconds 900 \
  --max-cycles 200 \
  --prompt-note "每一轮必须只做一个原子任务，必须写持久化播报，只有机器检查通过时才允许停止。"
```

监督器会持续刷新 `latest-status.txt`、`status-history.jsonl`、`latest-stop-report.json`、`run-summary.md`，避免看起来像卡死。

## 冰雹猜想示例 Prompt

这个例子很适合拿来压测，因为循环次数并不直观，而且你可以非常严格地限制“每轮只能算一步”。

```text
请使用 $strict-agent-loop 来处理这个仓库。
任务是从 27 开始构造冰雹猜想序列。
每一轮只允许计算并追加下一个数字，绝对不允许一轮里连算多步。
请把完整数列持久化到 output/sequence.json。
当数列最终到达 1 之后，再额外用一轮写 output/report.md，里面必须汇总完整数列。
只有当 python verify_hailstone.py 返回 0 时才允许停止。
每一轮都必须先播报、再执行、再验证、再落盘，并通过 strict-agent-loop 的脚本维护状态。
```

## 以后怎么问 Codex 才对

如果你之后直接问 Codex “`strict-agent-loop` 怎么用？”，一个合格回答至少应该包含：

- 一份交互模式快速开始
- 一份无人值守模式快速开始
- 所有关键持久化文件路径
- “无人值守最好依赖机器可检查停止条件”这个提醒
- 可以直接复制使用的 prompt 或 shell 命令

## 怎样设计好的停止条件

好的停止条件应该是窄的、外部可检查的，比如：

- `pytest -q`
- `ruff check .`
- `python verify_hailstone.py`
- `--require-path output/report.md`
- `--require-text "output/report.md::Sequence complete"`

不好的停止条件往往只依赖模型主观判断，比如：

- “感觉差不多了就停”
- “代码看起来没问题就停”
- “仓库大概能用了就停”

如果可以，最好在目标仓库里写一个很小的 verifier 脚本，让它成为主停止命令。

## 真实使用时的限制与建议

这个 skill 提供的是更严格的执行协议，不是新的 runtime。实际运行仍然会受 Codex 会话时长、工具可用性、认证状态、上下文长度等限制。为了让长任务和无人值守更稳，建议这样做：

- 把 `.codex-loop/` 放在目标仓库里，不要放临时目录。
- 只要磁盘状态和模型记忆不一致，一律以磁盘状态为准。
- 每一轮都尽量小到可以快速验证。
- 最好写一个 verifier 脚本，让它只有在真正完成时才返回 `0`。
- `max_iterations` 要尽量贴近现实。否则进度条和 ETA 只能是很粗的启发式估计。
- 无人值守模式下，`max_rounds_per_invocation` 不要太大，这样恢复点会更密。
- 如果你的环境里嵌套 `codex exec` 偶尔会卡住，给监督器加上 `--max-invocation-seconds`，让它超时后显式失败并重试，不要无限挂着。
- 每隔几轮，或者上下文明显变重时，主动跑一次 `compact_state.py`。
- 看进度时优先看 `latest-status.txt`、`status-history.jsonl`、`run-summary.md`，不要只盯着 Codex 控制台。
- 如果关键工具突然不可用，要明确记成 blocker，不要让任务静悄悄地漂掉。

## 仓库结构

```text
strict-agent-loop/
├── SKILL.md
├── README.md
├── README_zh.md
├── agents/openai.yaml
├── scripts/
│   ├── append_event.py
│   ├── check_stop.py
│   ├── compact_state.py
│   ├── init_state.py
│   ├── report_status.py
│   ├── state_tools.py
│   ├── stop_tools.py
│   ├── supervise.py
│   └── update_state.py
└── references/
    ├── modes.md
    ├── prompt_templates.md
    ├── protocol.md
    ├── recovery.md
    ├── state_schema.md
    └── stop_checks.md
```

## 验证方式

- 可以运行 `python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py /path/to/strict-agent-loop`。
- 可以先在临时仓库上直接跑这些生命周期脚本。
- 可以拿真实任务前向验证。冰雹猜想/Collatz 数列是很好的压力测试，因为它既能限制每轮只算一步，又要求最后汇总全量历史。
- 仓库里的 [python-compat.yml](./.github/workflows/python-compat.yml) 会对 Python `3.7` 到 `3.14` 做标准库脚本烟测。

`supervise.py` 本身没有在 CI 里做完整烟测，因为它依赖本机可用的 `codex` 命令以及有效的会话/认证环境。
