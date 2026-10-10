# AGENTS.md

本仓维护 `libeuicc` Apple framework 的构建与交付：根 CMake 直接编译 `lpac/euicc`，链接 `lpac/cjson`，生成公开头文件、版本接口和 Clang module，再由 CI 组合 XCFramework。路径均相对当前 checkout，适用于 linked worktree。

## 从任务进入

只读取与当前改动相关的入口；上游文档描述 lpac 本身，framework 的实际行为以根构建和产物为准。

| 任务 | 入口 |
| --- | --- |
| framework target、公开头文件、资源、安装或版本 | [CMakeLists.txt](CMakeLists.txt)、[版本声明](include/version.h.in)、[版本实现](include/version.c.in) |
| Clang module、Objective-C / Swift 导入 | [module.modulemap.in](module.modulemap.in)、根 CMake 生成的 umbrella header |
| eUICC 生命周期、APDU / HTTP 回调、协议实现 | [euicc.h](lpac/euicc/euicc.h)、[interface.h](lpac/euicc/interface.h)、`lpac/euicc/` 中相关实现 |
| Apple SDK、架构、deployment target 或 toolchain | [ios.toolchain.cmake](cmake/ios/ios.toolchain.cmake)、[工具链说明](cmake/ios/README.md) |
| 构建矩阵、XCFramework、ZIP、checksum 或 Release | [根 CI](.github/workflows/build.yaml)、[发布操作](docs/releases.md)、[构建脚本](scripts/ci/build-platform.sh)、[产物验证](scripts/ci/package.py) |
| 子模块来源或 lpac 开发约定 | [.gitmodules](.gitmodules)、[lpac README](lpac/README.md)、[开发说明](lpac/docs/DEVELOPERS.md) |

## 查证与事实源

<!-- codebase-memory-mcp:start -->
本项目使用 codebase-memory-mcp 维护知识图谱。代码结构发现始终优先使用 MCP 图工具；先确认项目、checkout 和索引覆盖，再按以下顺序选择工具：

1. `search_graph`：按名称或模式定位函数、类型、变量等。
2. `trace_path`：查调用者、被调用者与调用路径。
3. `get_code_snippet`：读取已定位函数或类型的源码。
4. `query_graph`：用 Cypher 查询复杂关系。
5. `get_architecture`：获取高层架构概览。

工具不可用、结果不足或索引与当前 checkout 不匹配时，限定范围回退 `rg` / 直接源码；字符串、错误消息、配置值和非代码文件可直接检索。图未命中不等于源码不存在。
<!-- codebase-memory-mcp:end -->

- 版本、target、打包内容与依赖以当前根 [CMakeLists.txt](CMakeLists.txt) 为准；默认版本由 `LIBEUICC_VERSION` 定义，构建可用 `LIBEUICC_VERSION_OVERRIDE` 覆盖，最终统一进入 `PROJECT_VERSION`。发布必须同时验证默认版本、lpac gitlink 与指定上游 tag 一致，不能由上游 CMake 版本推断。
- 工具链支持范围以锁定的 `cmake/ios` 源码为准；上游最新 README 和根 CI 的平台列表都不能代替当前版本的产物验证。
- 新增约定保持短而具体。文档用中文，函数名、路径、命令、配置键与平台值保留原文；不引用本机参考仓路径作为构建前提，也不创建指向尚不存在的 skills、测试或文档的路由。

## 所有权与兼容边界

- 根构建负责 Apple 包装；当前只使用 `lpac/euicc` 与 `lpac/cjson`，没有构建 lpac CLI 或 `lpac/driver` 后端。修改包装时不要引入整套 lpac 根构建及其驱动依赖；APDU / HTTP 通过公开回调接口由消费方提供。
- `lpac/` 与 `cmake/ios/` 是 Git 子模块。修改前分别核对状态，默认保留固定 gitlink；确需升级或修改时，说明来源、revision 与影响。子模块源码改动须在子模块中形成可复现提交，父仓记录相应 gitlink；不能把子模块中的未提交改动当作父仓已交付内容。
- `build/` 和其他构建目录属于生成区。umbrella `libeuicc.h`、`version.h`、`version.c`、`module.modulemap` 与 `libeuicc.pc` 的 owner 是根 CMake 和对应模板；修改 owner 后重新生成，不手改或提交产物。
- 公开头文件来自 `lpac/euicc/*.h`，当前只按 `*.private.h` 排除，再加入生成的 umbrella 与版本头。新增或移动头文件要重新 configure，并检查实际 `Headers` 和 module 导入；公开结构中名为 `_internal` 的字段仍影响布局，不能据此任意删除。
- 保持公开 C 函数签名、符号、结构布局、回调语义、返回码以及缓冲区的分配/释放约定。版本 getter、`euicc_ctx`、APDU / HTTP interface 的改动须验证消费方编译与链接；破坏性变化要明确说明兼容影响，不能混入包装整理。
- 核心 C 代码遵循上游 C99 风格；涉及二进制协议、长度转换、内存管理时检查边界与失败路径，明确 owner 和生命周期，不顺带重排无关代码。
- framework 的许可证资源由根 CMake 配置，`libeuicc-LICENSE` 与 `cjson-LICENSE` 是子模块内许可证的符号链接。保留许可证与版权声明；子模块升级或打包变更后核对链接和产物资源是否完整。

## 构建入口

在仓库根执行。构建需要 macOS、完整 Xcode、所需 Apple SDK 和 CMake；根要求 CMake 3.14+，锁定工具链的 Apple Silicon 平台（含 `MAC_UNIVERSAL`）要求 3.19.5+。先核对 `xcode-select -p`、`xcodebuild -version`、`cmake --version`；SDK 或签名失败按实际环境报告，不据此宣称源码失败。

首次 checkout 缺少子模块时使用 `git submodule update --init --recursive`，只恢复父仓锁定 revision；已存在本地改动时先核对状态，不用 `--remote` 代替初始化。

以下是与根 CI 一致的 macOS 平台构建入口。每个平台使用独立构建目录；Xcode 是多配置生成器，通过 `--config` 选择 Debug / Release：

```sh
cmake -S . -B build/agent-MAC_UNIVERSAL -G Xcode \
  -DCMAKE_TOOLCHAIN_FILE=./cmake/ios/ios.toolchain.cmake \
  -DPLATFORM=MAC_UNIVERSAL
cmake --build build/agent-MAC_UNIVERSAL --config Debug --target libeuicc
cmake --build build/agent-MAC_UNIVERSAL --config Release --target libeuicc
```

根 CI 将 iOS、tvOS、watchOS 的 device / simulator 分开构建，再加入 macOS universal，共七个 SDK 变体；架构、runner 和 Xcode 版本以 workflow 与验证脚本为准。只验证受影响平台，全矩阵用于整体交付。不要使用跨 device / simulator 的 `COMBINED` 产物代替 XCFramework 切片，也不能仅靠 CPU 架构推断平台身份。

## 最小验证与交付

| 修改面 | 必要验证 |
| --- | --- |
| 文档、agent 指令 | `git diff --check` 与变更 Markdown 本地链接检查；新增未跟踪文件另用 `git diff --no-index --check /dev/null AGENTS.md` 或暂存后检查 |
| CMake、版本模板或 framework 资源 | 重新 configure；受影响平台 Debug / Release 构建；核对 bundle 版本、生成头文件、module、许可证和安装结果 |
| 公开头文件、C ABI、module map | 相关平台构建；从实际 framework 编译并链接最小消费方，按改动覆盖 C、Objective-C 或 Swift 的导入与调用 |
| 协议、解析、回调或内存管理 | 聚焦公开行为和失败路径的可执行验证；使用脱敏 fixture / 回调替身，必要时在支持环境运行 ASan / UBSan |
| CI、平台组合或发布打包 | 受影响平台及 `xcodebuild -create-xcframework`；核对 XCFramework `Info.plist` 的平台/架构、Mach-O 切片、目录名大小写、ZIP 内容和实际 ZIP 的 `swift package compute-checksum` |

- 根构建当前没有注册 CTest 或独立自动化测试套件。`ctest` 零测试、configure 成功或本地编译通过，都不能作为协议、设备或全平台验证证据。
- 不新增读取源码、CMake、workflow 或文档原始文本并以 contains / 正则断言实现接线的测试。包装用真实编译、链接与产物；协议行为用可执行用例验证，不以静态文字匹配代替。
- 按需用 `plutil`、`file`、`lipo`、`otool`、`nm` 检查真实产物；设备与 simulator 的平台身份不能只靠 CPU 架构判断。签名、部署版本或构建参数变化也要核对最终 bundle / Mach-O。
- 交付写清变更范围、实际执行的命令和结果，以及未运行项和原因；区分文档检查、编译/导入/链接、打包与实机验证。不要把 CI 配置或上游功能说明写成已经通过的验收结论。
- 正式发布沿用 tag 模式：推送 `vMAJOR.MINOR.PATCH` tag 触发构建与发布，branch push / PR 和 `workflow_dispatch` 只验证。tag、根默认版本与上游 lpac gitlink 必须对应；完整验证两个配置的切片、版本、许可证、公开符号、消费方与 dSYM UUID 后才发布，既有正式 release 不覆盖。保留历史小写 ZIP / checksum 文件名；manifest 记录 wrapper、lpac 与 toolchain 的确切 SHA。

## Git 与设备数据

- 修改前后运行 `git status --short --branch --untracked-files=all`，同时核对受影响子模块状态，保留无关改动。提交仅暂存本任务路径，检查 `git diff --cached --check` 与 `git diff --cached --name-status`；遵循现有 `type(scope): subject` 提交风格。
- `codex/*` 分支只在本地使用，不推送到远端，包括显式 refspec、`--all` 或其他间接推送方式。完成验证后按授权将改动集成到正式分支，发布只推对应版本的 tag。已推送的临时分支在任务结束后按授权删除，先确认提交仍由正式分支或 tag 保留。
- 构建与交付产物放在专用构建目录，不提交 framework、XCFramework、ZIP、checksum、缓存或签名材料。
- 不打印或提交凭据、私钥、签名证书、激活码、确认码及未脱敏的设备标识、APDU / HTTP 载荷。启用 `LIBEUICC_DEBUG_APDU` 前确认数据范围；测试使用最小脱敏 fixture。
- 真实 profile 下载、启用/禁用、删除、notification 处理及远端发布按已有明确授权范围执行；文档整理或构建验证本身不构成这些操作的授权。

## 子代理策略

仅在当前任务允许委派且存在独立子任务时创建子代理。创建时显式传 `model`、`reasoning_effort`、`fork_turns="none"`，用最小简报交代任务、文件 owner、已有证据与验收条件。

| 任务 | 默认模型 | effort |
| --- | --- | --- |
| 常规实现、验证与文档 | `gpt-6-sol` | `medium` |
| 明确机械任务、只读检索 | `gpt-6-luna` | `low` |
| 复杂根因、ABI / 跨平台取舍、高风险审查 | `gpt-6-astra` | `high` |

用户指定优先；这些是协作取舍，以当前工具实际可用模型为准，不可用时说明限制，不静默替换。默认不使用 `xhigh`、`max` 或 `ultra`。仅将具体难点交给 Astra，常规后续回到 Sol；并发遵守平台容量，避免同时修改同一文件、子模块或争用同一构建目录，不重复已通过的验证。

本文件组织参考 [OpenAI AGENTS.md 指南](https://learn.chatgpt.com/docs/agent-configuration/agents-md)；framework 与公开头文件的打包语义参照 [CMake FRAMEWORK](https://cmake.org/cmake/help/latest/prop_tgt/FRAMEWORK.html) 和 [PUBLIC_HEADER](https://cmake.org/cmake/help/latest/prop_tgt/PUBLIC_HEADER.html)。外部资料复核日期：2026-10-10；仓库实际行为仍以当前源码和验证结果为准。
