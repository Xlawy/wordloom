# Git 与 Windows/Linux 同步

仓库根目录是 `wordloom/`。只同步应用源码、测试、脚本和文档；上一级 `input/`、`outputs/` 不在仓库中。虚拟环境、模型设置、本地词库、导出和验证产物均忽略。文档链接的 `validation/` 历史日志/截图是本机证据，不随 Git 同步；在目标平台运行验证脚本产生新日志。

## 首次连接 GitHub

在 GitHub 创建空仓库，不初始化 README、许可证或 .gitignore。将下面的 `OWNER/REPO` 替换为自己的仓库路径，在 Linux 项目目录执行：

```sh
git remote add origin https://github.com/OWNER/REPO.git
git push -u origin main
```

使用 Git 的凭据管理器或 SSH 完成认证，不在远程 URL 中嵌入访问令牌。当前初始化不代表已创建 GitHub 仓库或完成推送。

## Windows 首次克隆

在 Windows PowerShell 中，选择新的本地目录，保留旧手动复制目录直到确认新目录可运行：

```powershell
cd C:\Projects
git clone https://github.com/OWNER/REPO.git wordloom-git
cd wordloom-git
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -e .
.\.venv-win\Scripts\python.exe -m wordloom
```

虚拟环境是每个工作目录自己的，不能复制 Linux `.venv`。默认业务数据在 `%LOCALAPPDATA%\WordLoom`，不在源码目录；新克隆使用同一默认数据目录，启动前先退出旧实例。若以前指定 `--data-dir`，继续使用同一参数。

## 日常开发与更新

每次开始修改前先检查并更新：

```sh
git status
git pull --ff-only
```

开发端修改后，检查差异并明确选择文件：

```sh
git diff
git add src tests checks scripts docs README.md pyproject.toml
git diff --cached --stat
git commit -m "Describe the change"
git push
```

另一台机器退出应用后 `git pull --ff-only`，再用其自身虚拟环境启动。已有 editable 安装在源码更新后直接生效；只有依赖声明改变时才需要再次 `pip install -e .`。`.gitattributes` 统一源码换行，PowerShell 脚本在检出时使用 CRLF。

如果两端都有提交而无法快进，先保留双方修改，再处理合并；不要用强制推送或硬重置来覆盖另一端工作。Git 只同步源码，API Key 仍需分别在各操作系统的凭据库设置，词库需要另行导入/导出或备份。
