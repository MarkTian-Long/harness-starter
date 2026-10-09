# 发行与回退

当前为 0.2.0-rc.3 公开预发行候选。本文给出构建与核验步骤，不代替本候选的实际通过记录。
公共包名称沿用 harness-starter；每个人的私人 JSON 是数据，不是另一套公开发行。

## 未改动源码的构建

在公共源码根目录使用 Windows / Python 3.11+：

```powershell
python -B release.py
python -B tests/acceptance.py
```

release.py 要求源文件与 release-allowlist.json 精确匹配，仅忽略 .git、.qa、dist 和 __pycache__。
根 release-manifest.json 是生成文件，不列入源 allowlist；它记录清单中每份文件的字节数与 SHA-256。
内嵌清单与当前源字节不一致时会拒绝构建。同版本 ZIP 已存在而字节不同时也会拒绝，不能覆盖旧包。
dist/release-manifest.json 另带 archive 字段，用于核对 ZIP 摘要；它与根内嵌清单不是同一文件。

## 文本换行与新增文件

.gitattributes 使用 `* text=auto eol=lf`，公共文本按 UTF-8 / LF 保存；构建器按原始字节计算摘要，
不在打包时静默修正文档。新增或删除公共文件必须同步有序、无重复的 allowlist。
CI 工作流和公共文档也已纳入精确清单；以后增加文件仍须登记，.gitignore 不改变发行白名单。
当前仍使用一份公共源码清单，没有引入第二套打包接口。

## 修改源码后重生内嵌清单

仅对正在编辑的新候选源码执行下列步骤，先保留旧发行与原归档。不要直接修改旧发行 ZIP。

1. 完成所需源码修改；递增 VERSION 与 starter.py 的 VERSION，使二者一致。
2. 检查公开范围与 LF 换行，更新 release-allowlist.json。任务实例、私人文件和审计材料留在源码外。
3. 在新候选源码根目录运行下面的 PowerShell 代码。它在同级创建一个从未存在的构建目录，
   只复制 allowlist 输入，使用现有构建器生成新清单，再将 ZIP 中的清单写回当前候选。
   这一步明确更新生成文件，不取消正常构建时的过期清单检查。

```powershell
@'
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import starter as s

source = Path.cwd()
names = json.loads((source / "release-allowlist.json").read_text(encoding="utf-8"))
if names != sorted(set(names)):
    raise ValueError("Allowlist must be sorted and unique")
if (source / "VERSION").read_text(encoding="utf-8").strip() != s.VERSION:
    raise ValueError("Version mismatch")
inputs = {name: s.child(source, name).read_bytes() for name in names}
if any(b"\r" in data for data in inputs.values()):
    raise ValueError("Normalize public text to LF before regenerating")
stage = source.parent / ("harness-build-" + s.VERSION)
s.reject_link(stage)
stage.mkdir(exist_ok=False)
for name, data in inputs.items():
    target = s.child(stage, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
subprocess.run([sys.executable, "-B", "release.py"], cwd=stage, check=True)
archive = stage / "dist" / ("harness-starter-" + s.VERSION + ".zip")
with zipfile.ZipFile(archive) as package:
    generated = package.read("release-manifest.json")
if any(s.child(source, name).read_bytes() != data for name, data in inputs.items()):
    raise ValueError("Source changed during build; review before retrying")
s.child(source, "release-manifest.json").write_bytes(generated)
print(json.dumps({"version": s.VERSION, "manifest_sha256": s.digest(generated)}))
'@ | python -B -
```

构建目录已存在时命令会停止；选择新的、经核对的目录名或下一候选版本，不覆盖已有证据。
此脚本仅适用于当前全部为文本的 allowlist；若将来加入二进制源文件，需先更新换行分类与核验步骤。

4. 在候选源码根目录再次运行 `python -B release.py`，确认写回的内嵌清单通过正常检查。
5. 比较这次 ZIP 与隔离构建 ZIP 的 SHA-256，并运行 `python -B tests/acceptance.py`。
   验收包含重复构建、解压后重建、精确清单外文件拒绝和合成私人配置往返。

## Git 检出与发布前核验

源码初次发布前，在独立的干净 Git 检出中核对 LF 和构建摘要。Windows 上分别检查
core.autocrlf=true、false、input 的新检出；修改配置后继续使用旧工作目录不算重新检出。
与候选源码逐文件比较 allowlist 及生成的内嵌清单，再比较 ZIP；不能把保持原字节的解压重建
当作 Git 换行行为已经验证。本机检查结果在候选验收记录中单独报告，不据本说明推定通过。

提交前审阅实际暂存文件集合：公共源 allowlist 加根 release-manifest.json。
私人配置、任务材料、历史主题 work 和本地 .qa 不进入公共仓库或发行 ZIP。
敏感标记扫描仅作补充，不能替代来源审阅。MIT 只针对本公开范围，不覆盖旧私人包的第三方资产。

维护者将精确公共源码发布到 https://github.com/MarkTian-Long/harness-starter，
对应标签 v0.2.0-rc.3 的 Release 应标记为预发行（prerelease）。工作流仅验收，不自动发布。
发布时可附版本、运行环境、独立用例数、结果与 ZIP 摘要的脱敏记录，不上传完整私人审计目录。
目标电脑、全新助手规则加载、其他操作系统和真实任务表现仍需另行验证。


### 首次暂存必须包含空白 overlay

`templates/.gitignore` 的 `/private/` 是生成实例需要的保护规则；在源码仓库内它也会影响
`templates/private/overlay.md`，所以不能只用 `git add .` 准备初始提交。
在本仓库根目录按精确公共清单逐个加入文件，`--force` 仅作用于已经审阅的这些路径：

```powershell
$publicPaths = @(Get-Content -LiteralPath release-allowlist.json -Raw -Encoding UTF8 | ConvertFrom-Json)
$publicPaths += 'release-manifest.json'
foreach ($publicPath in $publicPaths) {
    git add --force -- $publicPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage an allowlisted path" }
}
@'
import json
from pathlib import Path
import subprocess
expected = set(json.loads(Path('release-allowlist.json').read_text(encoding='utf-8')))
expected.add('release-manifest.json')
tracked = set(subprocess.check_output(['git', 'ls-files', '-z']).decode('utf-8').split('\0')) - {''}
if tracked != expected:
    raise SystemExit('Git index differs from the exact public set; inspect before publishing')
print('Exact public index verified; blank overlay is included')
'@ | python -B -
```

不要改掉生成实例的私人忽略规则来规避这个问题，也不要对整个私人主题目录使用 force-add。
CI 会重新核对跟踪文件集合与 LF，但第一次上传前仍须先在本地检查。

## 升级与回退边界

本版没有原位升级器。旧安装继续用匹配的旧版脚本管理，新版在新空目录试用。
保留原包、原安装和用户修改；rollback 是卸载当前初始安装的别名，不是跨版本回退。
核心不自动迁移账号、运行时、权限或项目资料，也不自动同步两台机器。
