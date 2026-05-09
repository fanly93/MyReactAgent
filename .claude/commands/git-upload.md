# git-upload — 阶段代码上传命令

将当前阶段的代码和规范文档提交并推送到 GitHub，同时可选打版本 Tag。

## 使用方式

```
/git-upload [提交信息]
```

- `/git-upload` — 自动分析改动内容，生成中文提交信息
- `/git-upload 修复工具调用解析逻辑` — 直接使用该文本作为提交信息

## 重要规则（违反会导致分支分叉）

- **PR 合并后，功能分支立即冻结**：不再向该分支 push 任何新 commit，否则会产生与 main 的分叉。
- **新阶段必须从 main 切出新分支**：PR 合并完成后，下一阶段在新分支（如 `002-phase2-xxx`）上开发，不在旧分支继续。

## 执行步骤

### 1. 检查工作区状态

运行：
```bash
git status
git diff --stat HEAD
```

如果工作区**没有任何改动**，告知用户"当前没有需要提交的内容"并停止执行。

### 2. 确定提交信息

**情况 A：用户提供了参数 `$ARGUMENTS`**

直接使用 `$ARGUMENTS` 的内容作为提交信息主题，不做任何修改或补充。

**情况 B：用户没有提供参数（`$ARGUMENTS` 为空）**

自动生成提交信息，步骤如下：

1. 运行以下命令获取详细改动：
   ```bash
   git diff HEAD
   git diff --name-status HEAD
   ```
2. 仔细阅读改动的文件内容，分析：
   - 本次改动的核心目的（实现了什么功能、修复了什么问题、更新了什么文档）
   - 涉及的模块或目录（如 `myreactagent/`、`specs/`、`tests/`、`examples/`）
3. 按以下格式生成中文提交信息：
   ```
   <类型>: <一句话总结>

   - <具体改动点1>
   - <具体改动点2>
   - <具体改动点3>（如有更多则继续列出）
   ```
   类型从以下选择：`feat`（新功能）、`fix`（修复）、`docs`（文档）、`refactor`（重构）、`test`（测试）、`chore`（构建/配置）
4. 将生成的提交信息**展示给用户预览**，等待用户确认或提出修改意见，确认后再继续。

### 3. 暂存所有改动

```bash
git add .
git status
```

展示将要提交的完整文件列表。

### 4. 执行提交

使用第 2 步确定的提交信息创建 commit。

### 5. 推送到 GitHub

```bash
git push origin HEAD
```

### 6. 询问是否为阶段完成（创建 PR + 打 Tag）

询问用户：

> 本次是否为阶段完成？如果是，将创建 PR 合并到 main，并在 main 上打版本 Tag。[y/N]

**用户选择 N 或直接回车**：跳过，流程结束。

**用户选择 y**：执行完整阶段完成流程：

从当前分支名提取阶段编号（例如 `001-phase1-mvp-prototype` → `phase1`），建议 Tag 名为 `phase{N}-complete`。

1. 创建 PR（功能分支 → main）：
   ```bash
   gh pr create --base main --head <当前分支> --title "<提交信息主题>" --body "..."
   ```

2. 合并 PR：
   ```bash
   gh pr merge <PR编号> --merge --delete-branch=false
   ```

3. 切换到 main 并拉取最新代码：
   ```bash
   git checkout main && git pull origin main
   ```

4. 打 Tag 并推送（**Tag 必须打在 main 上**）：
   ```bash
   git tag -a phase{N}-complete -m "<提交信息主题> — $(date '+%Y-%m-%d')"
   git push origin main
   git push origin phase{N}-complete
   ```
   如果 Tag 已存在，告知用户并跳过，不强制覆盖。

5. 切回原功能分支（**此分支从此冻结，不再 push 新 commit**）：
   ```bash
   git checkout <原功能分支>
   ```

6. 告知用户：下一阶段开发请从 main 切出新分支：
   ```bash
   git checkout main && git checkout -b 00X-phaseX-<功能名>
   ```

### 7. 输出完成摘要

用中文展示：
- 本次提交的文件数量
- GitHub 分支链接：`https://github.com/fanly93/MyReactAgent/tree/<分支名>`
- 如果打了 Tag，附上链接：`https://github.com/fanly93/MyReactAgent/releases/tag/<tag名>`
