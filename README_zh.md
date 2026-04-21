# strict-agent-loop

[English README](./README.md) | 简体中文

> ⚠️ **已废弃（DEPRECATED），不再维护。**
>
> 这个 skill 已经停止维护，请不要再安装。下面分隔线以下的内容仅作为历史存档保留，
> 不会再有针对这个工作流的新版本。

## 应该改用什么

"严格原子轮次 + 磁盘状态"这一整套能力已经不值得以单独 skill 的形式维护。Codex 和
Claude Code 各自都已经有原生能力覆盖真实的使用场景。按你使用的 CLI 走对应路径即可。

### 如果你在 Codex CLI 上装过

1. 卸载：

   ```bash
   rm -rf "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
   ```

2. 已有 workspace 里的 `.codex-loop/` 目录现在是死数据。如果还想保留 event 历史，
   打个包即可：`tar czf codex-loop-archive.tgz .codex-loop/`，否则直接删掉。

3. 如果还想让 Codex 按严格原子步骤执行，不要再套 skill，直接用原生能力：

   - 把"每轮只做一件有界小事 + 一个可机器校验的完成条件"写进你的 prompt。
   - 用 Codex 自带的 session 恢复能力，替代自建的磁盘 loop。
   - 真需要持久化进度时，在 workspace 里自己写一个 append-only 日志文件就够了——
     比套 skill 简单，也不会漂移。

### 如果你试着在 Claude Code 上装过

这个 skill 从来没有为 Claude Code 发布过，现在也不推荐给任何 CLI。Claude Code 端
无需卸载。

如果你想在 Claude Code 上得到同样"严格原子轮次 + 磁盘状态"的效果，用原生特性：

- Task 系统（`TaskCreate` / `TaskUpdate` / `TaskList`）直接在会话中追踪原子轮次，
  不需要额外 runtime。
- `.claude/agents/` 里的 subagent 把每一轮隔离到独立上下文。
- Plan mode 强制 agent 在执行前先承诺一个有界计划。
- `settings.json` 里的 hooks（`SessionStart`、`PreToolUse`、`Stop`）可以覆盖
  "跨 session 持久化状态"这件事，不需要再单独写一个 runtime。

---

## 历史文档（不再维护）

以下章节描述原始（已废弃）skill。保留仅供审阅过去的使用记录，**不要再安装或运行**。

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

## 工作产物目录 vs 循环账本目录

这两个区域要明确分开：

- 真正的任务产物放在 `<workspace-root>/` 下面，比如 `src/`、`docs/`、`tests/`、`output/`。
- 循环自身的账本和控制面文件放在 `.codex-loop/tasks/<task-id>/`，包括 `state.json`、日志、stop report、轮次摘要等。

这个边界很重要，因为 prompt 如果写得含糊，Codex 很容易把真正的交付物错误地写进 task ledger 目录。除非你明确要求，否则 task root 只应该保存控制和恢复相关的文件。

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
把 /abs/path/to/repo 当作真正的工作区根目录。
把 /abs/path/to/repo/.codex-loop/tasks/parser-fix/ 只当作账本目录：里面只放状态、日志、stop report 和轮次摘要。
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
  --supervisor-reasoning-effort medium \
  --supervisor-max-rounds-per-invocation 5 \
  --supervisor-max-consecutive-failures 3
```

现在无人值守模式默认是“每次新起一个 Codex 调用，然后完全从磁盘恢复”。只有当你明确想跨调用复用同一个内层 Codex 线程时，才在初始化时额外加 `--supervisor-resume-existing-thread`。
如果你的 provider 在高峰期经常拒绝特别重的推理任务，建议把 `--supervisor-reasoning-effort` 设成 `low` 或 `medium`，可用性通常会更好。

再启动监督器：

```bash
python "$SKILL/scripts/supervise.py" \
  --state "$STATE" \
  --skill-path "$SKILL" \
  --heartbeat-seconds 30 \
  --max-invocation-seconds 1800 \
  --max-cycles 200 \
  --prompt-note "每一轮必须只做一个原子任务，必须把播报和状态写入持久化文件，只有 stop checks 通过或真实 blocker 被记录时才允许停止。"
```

监督器会持续刷新这个任务自己的进度播报，至少包括：

- 已完成轮次数
- 类似进度条的状态
- 最近几轮耗时
- 最近平均单轮耗时
- 在有足够信号时给出剩余时间估计

而且它会把内层 Codex 的播报、以及每条命令的开始/结束事件同步转发到外层 stdout，所以人即使只是盯着 supervisor 输出，也能判断它是在推进还是卡住。

如果你给 `supervise.py` 发 `SIGINT` 或 `SIGTERM`，它会先保存最新状态、写入中断事件，然后以退出码 `130` 结束，这样后面可以继续从同一个 managed task 恢复。

所以即使你人不在，也不会看起来像是卡死。

## 冰雹猜想 / Collatz 示例 Prompt

这个例子很适合做端到端压力测试，因为总轮次不直观，而且可以强制“每轮只能做一步”。

```text
请使用 $strict-agent-loop 来处理这个仓库。
这个仓库本身就是 workspace root。
请把 output/sequence.json 和 output/report.md 写在 workspace root 下面，不要写进 .codex-loop/tasks/<task-id>/ 里。
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
- 真正的工作产物放在 workspace root，`.codex-loop/tasks/<task-id>/` 只保留循环账本和控制面文件。
- 最好在目标仓库里写一个很小的 verifier 脚本，并把它设成主要 `--stop-command`。
- `--supervisor-max-rounds-per-invocation` 不要太大，这样 durable checkpoint 会更密。
- 无人值守默认是磁盘优先恢复。只有你明确想跨多次调用复用同一个 Codex 线程时，才启用 `--supervisor-resume-existing-thread`。
- 如果你更看重 `codex exec` 可用性，可以显式设置 `--supervisor-reasoning-effort low` 或 `medium`；留空则沿用你本机 Codex 默认配置。
- 给 `supervise.py` 配一个相对宽松但明确存在的 `--max-invocation-seconds`，这样慢一些的汇总轮次也能跑完，同时又能防止嵌套 Codex 调用无声挂住。
- 如果某次调用虽然超时或非零退出，但已经把已验证进度落盘了，supervisor 会保留这部分进度，而且不会把它继续累计成一次额外的 consecutive failure。
- 如果无人值守过程中真的遇到了只读文件系统写失败，supervisor 会自动关闭“复用旧线程”并在下一轮退回到新起调用 + 从磁盘恢复。
- 需要暂停时，直接对 supervisor 发 `Ctrl-C` 或 `kill -TERM`；它会记录中断、保存状态，并以 `130` 退出。
- supervisor 调 `codex exec` 时会带 `--skip-git-repo-check`，所以不会因为仓库不干净就直接拒绝跑。
- prompt 里最好明确要求 Codex 在初次恢复之后不要每一轮都重读整份 `TASK.md` 或整份 `state.json`，而是只检查当前需要的那几个工作区产物和最新状态切片。
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
│   ├── json_get.py
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
