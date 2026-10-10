# Framework 构建与发布

[GitHub Actions](../.github/workflows/build.yaml) 将 iOS、tvOS、watchOS 的 device / simulator 与 macOS 分别构建。每个变体生成 Debug、Release framework 和对应 dSYM，全部验证通过后组合两个 XCFramework。

| 变体 | PLATFORM | 架构 |
| --- | --- | --- |
| iOS device | `OS64` | arm64 |
| iOS simulator | `SIMULATORARM64` | arm64、x86_64 |
| tvOS device | `TVOS` | arm64 |
| tvOS simulator | `SIMULATORARM64_TVOS` | arm64、x86_64 |
| watchOS device | `WATCHOS` | arm64_32、arm64 |
| watchOS simulator | `SIMULATORARM64_WATCHOS` | arm64、x86_64 |
| macOS | `MAC_UNIVERSAL` | arm64、x86_64 |

workflow 固定 runner 与 Xcode 路径，实际 SDK 和工具版本会写入运行日志及 manifest。部分 watchOS 架构的最低部署版本会由 Apple 工具链提升；切片的真实平台身份与架构通过 Mach-O 检查，不能仅从构建参数推断。

## 本地与 CI 验证

根 [CMakeLists.txt](../CMakeLists.txt) 定义默认版本；`LIBEUICC_VERSION_OVERRIDE=X.Y.Z` 可以指定构建版本。所有版本 getter、bundle 版本和生成文件使用同一 `PROJECT_VERSION`。公开 C 符号保持可见，核心使用 C99。

本机 GitHub CLI 已由 Homebrew 安装，优先使用现有 `gh`，先用 `command -v gh` 确认，不重复安装。凭据由 CLI 和 Actions 处理，不写入仓库或日志。

push 到 main / dev，以及针对 main 的 PR，执行构建和打包验证，不发布。手动构建可选择精确 lpac stable tag，例如：

```sh
gh workflow run build.yaml --repo spancat/libeuicc-framework \
  --ref dev -f upstream_tag=v2.3.0
gh run list --repo spancat/libeuicc-framework --workflow build.yaml \
  --limit 5 --json databaseId,headSha,status,conclusion,url
```

取得运行 ID 后使用 `gh run watch RUN_ID --repo spancat/libeuicc-framework --interval 30 --exit-status`；失败日志用 `gh run view RUN_ID --repo spancat/libeuicc-framework --log-failed`。`RUN_ID` 替换为实际运行 ID。运行结论须核对 `headSha`，不能用其他提交的成功记录代替。

构建 artifact 先封装为 tar，保留 framework 的符号链接，再跨 job 传递。打包脚本验证两个配置各七个切片的 bundle 版本、头文件、module、许可证、公开符号、每架构 Mach-O 平台及 dSYM UUID，并从实际 macOS framework 编译、链接和运行 C、Objective-C、Swift 消费方。

## 创建新发布或补发

1. 核对上游正式 stable release 与本仓 release/tag 清单，限定缺失版本，不重建已发布资产。
2. 准备对应 framework 提交：根 `LIBEUICC_VERSION` 与上游 tag 版本一致，`lpac` gitlink 指向该 tag 的精确 commit；保留已验证的构建配方与锁定工具链。不要只修改构建参数却让发布标签指向另一版本的源码。
3. 在该提交创建 `vMAJOR.MINOR.PATCH` tag，并用 `git push origin TAG` 触发自动发布，`TAG` 换成实际版本。`codex/*` 只作本地工作分支，禁止推送；正式分支按授权集成。`workflow_dispatch` 用于独立构建验证，不能创建正式 release。
4. 用 `gh run watch` 等待全部构建、打包与发布终态；发布失败时读取具体 job 日志并修复原因。
5. 用 `gh release view UPSTREAM_TAG --repo spancat/libeuicc-framework --json assets,url,tagName` 核对公开资产，再核对该 tag 的根版本、lpac gitlink 和 manifest。

发布 tag 只接受 `vMAJOR.MINOR.PATCH`。准备阶段解析同名上游 tag 的不可变 SHA，验证根默认版本、lpac gitlink 与 tag 一致；发布 job 另核对远端 tag 指向本次 wrapper commit。完整产物验证后才创建 draft、上传五项资产、核对资产集合并公开发布；既有 release 会明确失败，已有 tag 必须匹配本次源码。失败遗留 draft 时，先检查所属运行、目标提交及上传资产，再处理本次创建的未发布内容，不删除或覆盖正式历史发布。

公开资产继续使用历史命名：

- `libeuicc-debug.xcframework.zip` 及 `.sha256`
- `libeuicc-release.xcframework.zip` 及 `.sha256`
- `libeuicc-manifest.json`

manifest 记录版本、upstream tag/SHA、framework wrapper SHA、toolchain SHA、Xcode / CMake 版本、平台架构及两个 ZIP 的 Swift Package checksum。checksum 从实际 ZIP 计算，发布 job 另验证下载后的包内容哈希。补发旧版不会按发布时间抢占 Latest；发布流程比较正式版本的语义版本号，并串行处理最终发布。

批量补发逐版推 tag，并等待上一版发布完成后再推下一版。当前 concurrency 默认只保留一个 pending 发布；避免同时堆积多个版本，导致等待中的 job 被替换。
