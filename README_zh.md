# strict-agent-loop

[English README](./README.md) | 简体中文

`strict-agent-loop` 是一个给 Codex 用的 skill，加上一套只依赖 Python 标准库的小型 runtime。它的目标是把“容易偷懒、容易跳步骤、容易把中间过程压成一句话”的长任务，改造成严格的原子轮次执行，并把状态、播报、日志和恢复信息全部落到磁盘。

仓库里的辅助脚本按兼容 Python `3.7` 到 `3.14` 的方式编写。

## 可直接复制给 Codex 的安装 Prompt

如果你想让 Codex 自己安装或更新这个 skill，并顺手做一遍最小验通，可以直接复制下面这段：

```text
请把 GitHub 仓库 https://github.com/HansBug/strict-agent-loop 安装或更新到我的 Codex skills 目录，目录名固定为 strict-agent-loop，然后在一个临时目录里做一次基于 managed layout 的最小验证。

要求：
- 安装到 "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
- 如果目录已经存在，就 pull 最新 main，而不是重新 clone
- 后续校验命令统一使用 `SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"`
- 依次运行：
  1. python "$SKILL_DIR/scripts/init_state.py" --workspace-root <tmpdir> --task-id smoke --goal "Managed layout smoke test" --global-stop-condition "只有当 smoke 任务被正确初始化时才允许停止。" --success-evidence "registry 和 task-local state 都存在"
  2. python "$SKILL_DIR/scripts/list_tasks.py" --workspace-root <tmpdir>
  3. python "$SKILL_DIR/scripts/show_task.py" --workspace-root <tmpdir> --task-id smoke --json
- 确认 <tmpdir>/.codex-loop/registry.json 和 <tmpdir>/.codex-loop/tasks/smoke/state.json 都存在
- 把实际执行的命令和结果告诉我
```

## 这个 Skill 解决什么问题

- Codex 做长任务时容易把中间过程压缩成一句“搞定了”。
- 你希望每一轮都只能做一个边界明确的小任务。
- 你希望每一轮都必须先播报、再执行、再验证、再落盘。
- 你希望关键信息必须写入文件，而不是纯靠模型记忆。
- 你希望无人值守时，外层 while 能跨越多个 Codex 调用继续跑。
- 你希望一个仓库能同时挂很多不同循环任务，所以必须有任务管理和命名空间，不能全挤在一个默认状态文件里。

## 它怎么工作

这个 skill 并不是给 Codex 塞了一个真正“无限 while runtime”。它是通过三层东西把严格循环落地：

1. 控制器协议
2. 磁盘持久化状态和追加式账本
3. 可选的外层监督器

它支持两种模式：

- `interactive`：当前 Codex 会话就是控制器，对用户逐轮播报
- `unattended`：`scripts/supervise.py` 持有外层重复调用逻辑，反复运行或恢复 Codex

两种模式下，内层循环都遵守同一套协议：

1. 从磁盘读取权威任务状态
2. 宣布下一轮的唯一原子任务
3. 只做这一件小事
4. 用证据验证结果
5. 把这一轮写入持久化账本
6. 重跑机器可检查的停止条件
7. 刷新进度播报和汇总文件
8. 在没到停止条件前继续循环，直到停止条件或真实 blocker 出现

## Managed Task 布局

一个仓库可以同时有很多个 strict loop。默认布局是 manager + task root：

```text
<workspace-root>/
└── .codex-loop/
    ├── registry.json
    └── tasks/
        ├── parser-fix/
        │   ├── state.json
        │   ├── events.jsonl
        │   ├── iterations.jsonl
        │   ├── status-history.jsonl
        │   ├── latest-status.txt
        │   ├── latest-stop-report.json
        │   ├── run-summary.md
        │   ├── rounds/
        │   └── supervisor/
        └── docs-cleanup/
            └── ...
```

其中：

- `registry.json` 是任务管理索引
- 每个 `tasks/<task-id>/` 都是一个独立任务的完整持久化根目录
- 所有写操作都针对某一个明确的 `state.json`

这就是避免冲突的关键：

- 一个仓库可以同时跑很多任务
- 每个任务有自己的 `task-id`
- 变更型脚本都要求显式 `--state`
- `list_tasks.py` 和 `show_task.py` 负责做轻量管理

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

## 任务管理

建议每个长期目标都建成一个 managed task。只要你知道后面可能恢复、监督、查询，就尽量手动给一个稳定的 `task-id`。

同一个仓库里初始化两个不同任务：

```bash
REPO=/abs/path/to/repo
SKILL=/path/to/strict-agent-loop

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id parser-fix \
  --goal "以严格原子步骤修复 parser 缺陷。" \
  --global-stop-condition "只有当 pytest 通过且 parser 回归测试存在时才允许停止。" \
  --success-evidence "pytest -q passes" \
  --stop-command "pytest -q" \
  --require-path tests/test_parser_regression.py

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id docs-cleanup \
  --goal "以严格原子步骤整理发布文档。" \
  --global-stop-condition "只有当最终 release note 存在且包含必须摘要时才允许停止。" \
  --success-evidence "release note written" \
  --require-path docs/release-note.md \
  --require-text "docs/release-note.md::Release summary"
```

查看和检查任务：

```bash
python "$SKILL/scripts/list_tasks.py" --workspace-root "$REPO"
python "$SKILL/scripts/show_task.py" --workspace-root "$REPO" --task-id parser-fix
```

如果你不提供 `--task-id`，`init_state.py` 会根据 goal 和时间戳自动生成一个。

## 交互模式快速开始

先初始化任务：

```bash
REPO=/abs/path/to/repo
TASK_ID=parser-fix
STATE="$REPO/.codex-loop/tasks/$TASK_ID/state.json"
SKILL=/path/to/strict-agent-loop

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id "$TASK_ID" \
  --goal "以严格原子步骤安全修复 parser。" \
  --global-stop-condition "只有当 pytest 通过、回归测试存在且缺陷已修复时才允许停止。" \
  --success-evidence "pytest -q passes" \
  --next-task "先用一个最小、可验证的步骤复现 parser 的失败行为。" \
  --stop-command "pytest -q" \
  --require-path tests/test_parser_regression.py
```

然后明确告诉 Codex：

```text
请使用 $strict-agent-loop 来处理这个仓库。
开始前先读取 /abs/path/to/repo/.codex-loop/tasks/parser-fix/state.json。
本次使用 interactive 模式。
每一轮开始前，必须先告诉我：
- 当前是第几轮
- 之前已经完成了多少轮已验证任务
- 这一轮唯一要做的原子任务是什么
- 这一轮的完成条件是什么
- 全局停止条件是什么
- 满足什么条件这一轮之后就可以停止
- 如果已经有数据，就顺便告诉我最近几轮平均耗时和大致 ETA
然后把同样的信息写入这个任务自己的 events.jsonl。
每一轮完成后，必须先验证，再运行 check_stop.py，然后运行 report_status.py。
不允许擅自扩大范围，也不允许在 stop checks 没过时提前宣称完成。
```

## 无人值守模式快速开始

先初始化为无人值守模式：

```bash
REPO=/abs/path/to/repo
TASK_ID=nightly-parser-fix
STATE="$REPO/.codex-loop/tasks/$TASK_ID/state.json"
SKILL=/path/to/strict-agent-loop

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id "$TASK_ID" \
  --operating-mode unattended \
  --goal "在不偷懒的前提下，以严格原子步骤完成排队中的 parser 任务。" \
  --global-stop-condition "只有当 python verify_task.py 返回 0 且 output/final-report.md 存在时才允许停止。" \
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
python "$SKILL/scripts/supervise.py" \
  --state "$STATE" \
  --skill-path "$SKILL" \
  --heartbeat-seconds 30 \
  --max-invocation-seconds 900 \
  --max-cycles 200 \
  --prompt-note "每一轮必须只做一个原子任务，必须把播报和状态写入持久化文件，只有 stop checks 通过或真实 blocker 被记录时才允许停止。"
```

监督器会持续刷新这个任务自己的进度播报，至少包括：

- 已完成轮次数
- 类似进度条的状态
- 最近几轮耗时
- 最近平均单轮耗时
- 在有足够信号时给出剩余时间估计

所以即使你人不在，也不会看起来像是卡死。

## 冰雹猜想 / Collatz 示例 Prompt

这个例子很适合做端到端压力测试，因为总轮次不直观，而且可以强制“每轮只能做一步”。

```text
请使用 $strict-agent-loop 来处理这个仓库。
任务是从 27 开始构造冰雹猜想序列。
每一轮只允许计算并追加下一个数字，绝对不允许一轮里连算多步。
请把完整数列持久化到 output/sequence.json。
当数列最终到达 1 之后，再额外用一轮写 output/report.md，里面必须根据磁盘上的完整历史汇总整个数列。
只有当 python verify_hailstone.py 返回 0 时才允许停止。
每一轮都必须先播报、再执行、再验证、再落盘，并通过 strict-agent-loop 的脚本刷新状态。
```

## 给真正长时间无人值守任务的建议

这个 skill 比普通 prompt 严格得多，但实际执行仍然会受 Codex 会话时长、工具可用性、认证状态、上下文长度等限制。想让它在你不在的时候尽量稳，建议这样用：

- 每个无人值守目标都给一个稳定 `task-id`，不要今天一个名字、明天一个名字。
- 把任务状态放在目标仓库自己的 `.codex-loop/` 里，不要放临时目录。
- 最好在目标仓库里写一个很小的 verifier 脚本，并把它设成主要 `--stop-command`。
- `--supervisor-max-rounds-per-invocation` 不要太大，这样 durable checkpoint 会更密。
- 给 `supervise.py` 配上 `--max-invocation-seconds`，防止嵌套的 Codex 调用无声挂住。
- 看进度时优先看 `latest-status.txt`、`status-history.jsonl`、`run-summary.md`，不要只盯控制台。
- 如果上下文明显变重，就跑 `compact_state.py`。
- 需要恢复时，优先复用同一个 `state.json`，不要随手新建一个任务把旧账本切断。
- 同一个仓库里如果同时挂了多个 loop，用 `registry.json`、`list_tasks.py`、`show_task.py` 来找对任务，别手工猜。
- 如果你的 stop checks 是纯二值的，进度条和 ETA 就只能是启发式估计，所以 `max_iterations` 最好设得接近现实。

## 以后如果你直接问 Codex “这个怎么用”

一个合格回答至少应该包含：

- 一份交互模式快速开始
- 一份无人值守模式快速开始
- `.codex-loop/registry.json` 和 `.codex-loop/tasks/<task-id>/` 这套 managed layout
- 关键持久化文件都放在哪里
- “无人值守最好依赖机器可检查停止条件”这个提醒
- 能直接复制执行的命令或 prompt，而不是只讲概念

## 仓库结构

```text
strict-agent-loop/
├── AGENTS.md
├── SKILL.md
├── README.md
├── README_zh.md
├── agents/openai.yaml
├── scripts/
│   ├── append_event.py
│   ├── check_stop.py
│   ├── compact_state.py
│   ├── init_state.py
│   ├── list_tasks.py
│   ├── report_status.py
│   ├── show_task.py
│   ├── state_tools.py
│   ├── stop_tools.py
│   ├── supervise.py
│   └── update_state.py
└── references/
    ├── management.md
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
- 冰雹猜想 / Collatz 是很好的真实前向验证，因为它能抓出“偷着批量算多步”和“最后总结没真正汇总全历史”这两类问题。
- 仓库里的 GitHub Actions workflow 会对 Python `3.7` 到 `3.14` 做标准库脚本烟测。
- 其中 Python `3.7` 使用 `ubuntu-22.04`，因为更新的 Ubuntu runner 往往不再稳定提供 3.7。

`supervise.py` 本身没有在 CI 里做完整烟测，因为它依赖本机可用的 `codex` 命令，以及有效的会话或认证环境。
