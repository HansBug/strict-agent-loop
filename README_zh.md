# strict-agent-loop

[English README](./README.md) | 简体中文

`strict-agent-loop` 是一个用于 Codex 的 skill，目标是把那些容易被“跳步骤”或者“偷工减料”的任务，强制变成严格的小步循环执行。它把当前代理作为控制器，把一个持久子代理作为执行器，再配合磁盘状态账本，让任务在满足明确停止条件之前持续推进。

## 它强制的行为

- 每一轮只能做一个原子任务。
- 每一轮开始前都必须先对用户说明当前任务和停止条件。
- 第一轮执行时，用继承当前上下文的持久执行代理。
- 把状态写入 `.codex-loop/state.json`，而不是只靠上下文记忆。
- 每一轮之后都要做验证和停止条件检查。
- 如果代理丢失，就通过紧凑快照恢复，而不是从头来过。

## 仓库结构

```text
strict-agent-loop/
├── SKILL.md
├── README.md
├── README_zh.md
├── agents/openai.yaml
├── scripts/
│   ├── init_state.py
│   ├── update_state.py
│   ├── check_stop.py
│   ├── compact_state.py
│   └── state_tools.py
└── references/
    ├── protocol.md
    ├── prompt_templates.md
    ├── state_schema.md
    └── recovery.md
```

## 安装方式

### 方式一：安装到 Codex skills 目录，支持自动发现

把仓库 clone 到 Codex 的 skills 目录：

```bash
git clone https://github.com/HansBug/strict-agent-loop "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
```

安装后，就可以直接按 `$strict-agent-loop` 调用。

### 方式二：放在任意路径，通过显式路径调用

```bash
git clone https://github.com/HansBug/strict-agent-loop /path/to/strict-agent-loop
```

调用时写明 skill 路径：

```text
请使用位于 /path/to/strict-agent-loop 的 $strict-agent-loop 来帮助处理这个任务。
```

## 调用方式

这个 skill 适用于你希望 Codex 以严格小步循环方式推进任务，并且在全局停止条件满足之前不允许提前结束的情况。

示例：

```text
请使用 $strict-agent-loop 以严格原子步骤重构这个仓库。
每一轮开始前，先告诉我这一轮的精确任务、这一轮的完成条件，以及全局停止条件。
请在仓库根目录创建并持续维护 .codex-loop/state.json。
请始终复用同一个持久执行代理。
只有当 pytest 通过、lint 通过，并且本次要求的重构完成时，才允许停止。
```

显式路径调用示例：

```text
请使用位于 /abs/path/to/strict-agent-loop 的 $strict-agent-loop 来修复这个仓库里的 bug。
每一轮只做一个原子任务。
第一次创建执行代理时，请继承当前上下文。
在失败用例修复完成并补上一条回归测试之前，不要停止循环。
```

## 辅助脚本

初始化状态账本：

```bash
python scripts/init_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --goal "安全修复已报告的 bug" \
  --global-stop-condition "只有当 bug 修复完成、回归测试存在且 pytest 通过时才允许停止。" \
  --workspace-root /abs/path/to/repo \
  --success-evidence "pytest passes"
```

追加一轮已经验证过的执行记录：

```bash
python scripts/update_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --task "修复空输入时的 parser 行为" \
  --local-done-condition "空输入时 parser 能抛出预期错误" \
  --result-summary "parser 现在会对空输入抛出 ValueError" \
  --verification-summary "已通过针对 parser 边界条件的 pytest 验证" \
  --next-task "给 CLI 入口补充回归测试"
```

如果当前执行代理是第一次从当前上下文继承创建的，可以额外加上 `--executor-inherited-context`。
如果执行代理中途丢失并被替换，可以在下一次状态更新时加上 `--agent-id <new_id> --recovery`。

检查循环是否应当停止：

```bash
python scripts/check_stop.py --state /abs/path/to/repo/.codex-loop/state.json
```

压缩历史记录，供恢复使用：

```bash
python scripts/compact_state.py --state /abs/path/to/repo/.codex-loop/state.json
```

## 预期控制流

1. 当前代理充当控制器。
2. 控制器先明确目标和全局停止条件。
3. 控制器初始化 `.codex-loop/state.json`。
4. 控制器创建一个继承当前上下文的执行代理。
5. 每一轮只派发一个原子任务。
6. 控制器验证结果、更新状态，并检查是否停止。
7. 如果执行代理丢失，就从紧凑快照恢复并继续。

## 限制

这个 skill 提供的是更严格的执行协议，而不是新的 runtime。它可以显著减少偷懒和中间步骤压缩，但不能保证数学意义上的“真正无限循环”，因为实际执行仍然受 Codex 会话时长、工具可用性和上下文长度限制。

## 面对实际限制时的建议

为了让这套循环在真实会话里更稳，建议这样使用：

- 把全局停止条件写得具体且可复验。最好的停止条件是 `pytest 通过`、`某个文件完成更新`、`补上一条回归测试` 这种可以直接检查的条件。
- 把每一轮控制得足够小，保证一轮之内就能完成验证。如果一轮听起来像一个里程碑，那它通常还是太大了。
- 把状态文件写进目标仓库，而不是临时目录。这样即使会话中断，也能低成本恢复。
- 每隔几轮，或者在出现较大 diff 之后，主动运行一次 `compact_state.py`，避免上下文过长导致恢复成本上升。
- 事先约定什么算真正的 blocker，什么算工具缺失。如果某个关键工具不可用，要把它明确记进状态，而不是让循环悄悄失真。
- 优先选择控制器可以直接重跑的成功证据，比如 `pytest -q`、`npm test`、`ruff check`，或者对关键文件的简短 diff 检查。
- 如果任务本身很大，建议一开始就明确 `max_iterations` 和 `max_no_progress_rounds`，让循环在退化时能够显式失败，而不是拖着变形。

如果你预计会跑很长一轮任务，一个比较稳妥的默认做法是：

- 把 `.codex-loop/state.json` 放在仓库根目录
- 每完成 5 到 10 轮已验证步骤，就压缩一次状态
- 每个活动任务只保留一个执行代理
- 一旦记忆和真实仓库状态不一致，以磁盘状态为准

## 本地验证

这个仓库建议这样验证：

- 运行 `python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py /path/to/strict-agent-loop`
- 在一个独立的小型测试仓库里，用真实 Codex 任务前向测试
