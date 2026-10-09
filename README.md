# Harness：一套核心，每个人自己的配置

这是一个本地文件式 AI 协作套件，适合调研、写作、产品规划和需要中断续接的任务。
默认采用作者提炼的协作风格、通用 SOP 和恢复记录；也能选择最简模式。
Python 工具负责初始化与文件检查，实际任务由你选择的 Codex 或其他助手完成。
需要 Python 3.11+；当前验证范围以 Windows 为主，具体结果见对应候选的验收记录。

当前版本为 0.2.0-rc.3，预发行候选（RC），用于试用、复核与反馈。
公共源码：[MarkTian-Long/harness-starter](https://github.com/MarkTian-Long/harness-starter)。
本版本附件：[v0.2.0-rc.3 Release](https://github.com/MarkTian-Long/harness-starter/releases/tag/v0.2.0-rc.3)。
它不提供模型、账号、后台自动执行、全局安装器、双机同步或原位升级器。

## 我该选什么？

| 情况 | 操作 | 得到什么 |
| --- | --- | --- |
| 第一次使用，愿意沿用默认方式 | 默认初始化 | 协作风格、通用 SOP、任务与续接模板 |
| 只想有个简单任务入口 | 初始化时加 --preset minimal | 基础协作规则、任务说明和资料目录 |
| 已有自己的私人配置，或本人换电脑 | 初始化时加 --profile 指定文件 | 同一套核心，加自己的偏好和画像快照 |
| 想改个性化内容 | 编辑 private/overlay.md 和可选 private/profile.md | 私人调整保留在本地；需要时单独导出 |

“默认”是协作方法，不是作者的个人身份，也不继承作者的操作授权。
先读生成目录里的 FIRST_USE.md；默认风格可整体采用，无需填写一份长问卷。
私人文件不是公开发布材料；不把密钥、业务原文、聊天或账号放进去。

## 从 ZIP 或源码开始

- **使用发行 ZIP**：从本版本 Release 下载 `harness-starter-0.2.0-rc.3.zip`，核对附带摘要，解压到独立目录，在包含 starter.py 的目录运行下列命令。GitHub 自动生成的 Source code 附件属于源码快照。
- **使用公共源码**：克隆本仓库并检出对应标签，进入包含 starter.py、VERSION 和 release-allowlist.json 的源码根目录；可以直接试用，也可以按文末命令构建 ZIP。

```powershell
git clone https://github.com/MarkTian-Long/harness-starter.git
cd harness-starter
git checkout v0.2.0-rc.3
```

示例把任务目录放在源码或解压目录旁，避免任务材料混入公开源目录。在 PowerShell 中运行：

```powershell
New-Item -ItemType Directory ../my-harness
python -B starter.py init ../my-harness
python -B starter.py init ../my-harness --apply
python -B starter.py doctor ../my-harness
```

初始化目标必须是新建的空目录。默认只预览，加 --apply 才写入。
默认推荐模式已包含续接模板；最简模式需要时可加 --recovery。
初始化不写入全局 Codex 配置，也不覆盖或原位升级既有安装。

把目标目录交给助手，复制这句话即可开始：

> 请先读这个目录的 AGENTS.md 和 FIRST_USE.md。默认采用推荐协作方式，帮助我把本次目标、输入和完成条件写进 task.md，再完成任务。只读取适用的 SOP；个人事实由我提供，工具权限按当前环境处理。中断时记录下一步。

可选的离线工具示例：

```powershell
python -B starter.py demo ../my-harness --apply
python -B starter.py recover ../my-harness
```

示例结果为 count=3、total=10，只验证本地工具流程，不代表 AI 任务质量。

## 一套核心如何组织

| 文件或目录 | 作用 |
| --- | --- |
| AGENTS.md | 薄入口：按当前任务路由到适用资料 |
| FIRST_USE.md | 首次选择、可以改什么、怎样开始 |
| profile/style.md | 推荐协作风格；最简模式不装 |
| standards/ | 按需使用的通用 SOP；最简模式不装 |
| task.md | 当前任务的目标、权威输入和完成条件 |
| workspace/ | 项目材料与成果，各项目保持自己的正式入口 |
| personal/ | 与当前工作项目分开的个人实验 |
| private/ | 自己的偏好和可选画像；始终保留、不公开 |
| recovery/checkpoint.md | 当前进度、未完成项、下一步；不是全部聊天备份 |

默认方法和私人调整不需要复制成第二套核心。现有成熟项目继续使用自己的规则，
不要在项目里再建重复台账。详情见 [模块说明](docs/modules.md) 和 [迁移范围](docs/migration.md)。

## 本人换电脑：导出与导入私人配置

在旧电脑编辑已初始化目录中的私人偏好和画像文件，然后从匹配版本的核心目录运行：

```powershell
python -B starter.py export-profile ../my-harness --output ../my-profile.json
python -B starter.py export-profile ../my-harness --output ../my-profile.json --apply
```

输出须是新文件，并放在任务目录之外；示例同时将它放在公共源码目录之外。
它只收集 private/overlay.md 和可选的 private/profile.md，不收集任务、公司资料、
Skills、账号、权限设置或聊天。输出是未加密的私人 JSON，只通过本人信任的方式传递。

新电脑准备同一个公开发行包，把私人 JSON 单独放在包目录旁，再运行：

```powershell
New-Item -ItemType Directory ../my-harness
python -B starter.py init ../my-harness --profile ../my-profile.json
python -B starter.py init ../my-harness --profile ../my-profile.json --apply
python -B starter.py doctor ../my-harness
```

这是显式的快照导出/导入，不是双向同步、冲突合并或自动升级。
导入不是自动确认画像事实，也不是授权；账号、运行时、路径和工具在新机核验。
旧私人工具包是已有者的可选历史资产，普通新用户不需要它，详见 [迁移范围](docs/migration.md)。
新机须让助手显式读取规则并完成一个真实小任务，才能判断实际可用。

## 检查、续接与退出

doctor 检查文件可用性与发行状态，不判断正文正确性。正常修改不会让任务变成不可用；
缺少必需文件、损坏状态或不安全路径会失败。recover 只在可用时给出续接入口。

```powershell
python -B starter.py uninstall ../my-harness
python -B starter.py uninstall ../my-harness --apply
```

rollback 是卸载初始安装的别名，不是历史版本恢复。只删除未修改的受管公共模板；
private 下文件、你改过的文件和未登记文件全部保留，相应 .gitignore 保留。
因此退出后目录可以非空。无服务、后台任务或全局配置需要撤销。
不同发行的安装状态仍由对应旧发行管理；升级时保留旧目录，在新空目录试用。

## 源码构建、验证与分发

在保持清单一致的公共源码根目录运行：

```powershell
python -B release.py
python -B tests/acceptance.py
```

构建产物是 dist/harness-starter-0.2.0-rc.3.zip，以及包含 ZIP 摘要的 dist/release-manifest.json。
acceptance 会在源码与 ZIP 解压目录运行同一组单测并验证文件生命周期；重复运行不算新增独立用例。
修改源码后必须更新版本、精确清单与生成的内嵌 manifest，步骤见 [发行与回退](docs/release.md)。

公共仓库可发布 release-allowlist.json 列出的源码与生成的根 release-manifest.json；
Release 附件使用 dist 中对应版本的 ZIP。不要上传整个历史主题目录、私人配置、任务实例或 .qa。
MIT；第三方 Skills 实现不随公开包捆绑，见 [来源说明](docs/provenance.md)。

本版本仍为预发行。GitHub Actions 只运行验收，不自动创建 Release。
本地与云端结果分别查看 [公开验证说明](docs/VALIDATION.md) 和对应提交的 Actions；定义工作流不代表已经通过。
尚未据此确认新机助手自动加载、真实任务效果或其他操作系统支持。
[验证范围](docs/QA.md) 说明测试覆盖；[权限与数据边界](docs/security.md) 说明限制。

## 交流与改进

欢迎通过 [Issues](https://github.com/MarkTian-Long/harness-starter/issues) 分享脱敏的失败样例或方法改进。
通用经验经试用后回到公共核心，个人偏好与画像独立保管，项目资料留在各自项目；
不要把机器路径、账号或业务原文作为示例提交。具体见 [贡献说明](CONTRIBUTING.md)。
