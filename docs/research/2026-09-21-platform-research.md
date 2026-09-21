# 平台与技术路线调研

核验日期：2026-09-21。范围：公开官方文档、AOSP 源码及项目源码；**没有真机、模拟器或模型调用实验结果**。下文区分来源直接支持的事实、据此作出的工程判断，以及待验证项。

## 1. 结论与用户设备条件

用户目前有 iOS 设备，没有 Mac，已确认以电脑 Android 模拟器为主要开发、测试和演示环境；真机不一定能取得，因此列为可选补验，不作为推进前提。使用 Android Studio 官方模拟器，不必为此购买 Mac。

| 环境 | 能做什么 | 本题的主要限制 | 当前决定 |
| --- | --- | --- | --- |
| Android 模拟器，单个 AVD | 完整开发 APK、ADB 能力接口、日历读写，探索同实例副屏 | 没有证明 OEM 真机行为，原题物理手机部署项未覆盖 | **主要开发与演示目标** |
| 无 root Android 真机 | 预授权系统数据接口；shell 副屏路线有源码依据 | OEM 权限、资源负载、目标 App 兼容性要测 | 可选补验 |
| iPhone + 无 Mac | 快捷指令可做限定动作原型；已有 App 的后台能力可尝试 | 自研原生 App 的常规构建/签名/调试不方便；没有通用独立 GUI 操作空间 | 不作为首版主线 |
| iPhone + Mac/Xcode | 原生 App、EventKit、有限后台任务、WDA 测试 | 后台执行与界面隔离限制仍然存在，Mac 不会解除它们 | 后续受限能力分支 |

“两个模拟器分别给人和 Agent 用”是两台逻辑设备；“一个模拟器前台给人用、同实例后台执行”才是本版要证明的并发能力。后续若宣称支持真机，需要再在该真机复验；模拟器版交付本身不等待真机。[R5]

## 2. Android：先绕开共享输入资源

### R1. ContentProvider 可以作为按需执行入口

来源：

- [Android：创建内容提供程序](https://developer.android.com/guide/topics/providers/content-provider-creating)
- [Provider 清单配置](https://developer.android.com/guide/topics/manifest/provider-element)
- [AOSP Android 14 content 命令](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/cmds/content/src/com/android/commands/content/Content.java)
- [AOSP ContentProviderHelper](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/am/ContentProviderHelper.java)

**事实：**官方文档说明 Provider 在 `ContentResolver` 尝试访问时按需创建；`onCreate()` 应避免长操作。AOSP 的 `content call/read/write` 获取外部 Provider，调用 `call` 或 `openFile`。Provider 不在运行时，系统路径可以以 `HOSTING_TYPE_CONTENT_PROVIDER` 启动进程，而不是启动 Activity。源码还明确处理外部 shell 客户端等待 Provider 发布。

**判断：**电脑通过 ADB 请求手机端小型能力，无须先把 Companion 拉到前台；模型等待放在电脑，不需要手机常驻服务。这是设计首选。

**待验证：**目标 ROM 的 shell 访问、首次安装后的初始化、正常进程回收后冷启动、授权状态、流式数据与命令超时。不能把“应用被正常回收”与“用户 force-stop 后的 stopped 状态”混为一谈；后者单独测试并允许要求用户任务前手动重新启动应用。

### R2. Provider 的安全边界由应用实现

来源：

- [AOSP ContentProvider.java](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/core/java/android/content/ContentProvider.java)
- [Android：内容提供程序基础知识](https://developer.android.com/guide/topics/providers/content-provider-basics)

**事实：**`call()` 文档警告框架不知道自定义方法是否读写，实现需要自行做权限检查。`ContentProvider.clearCallingIdentity()` 同时处理 Binder 身份和调用者 attribution。

**判断：**演示桥必须先检查原始 caller UID，再在自身授权范围内操作；所有接口都限制媒体 ID、时间范围、日历、字段和文件路径。只设置 `exported=true` 或只限制 ADB 连接远远不够。`call`、`query` 和文件流入口都要受控。

### R3. 系统日历支持不拉起界面的真实读写

来源：[Android Calendar Provider](https://developer.android.com/identity/providers/calendar-provider)

**事实：**拥有 `READ_CALENDAR` / `WRITE_CALENDAR` 的应用可直接查询、新增、修改日历事件。官方区分数据 API 与 Calendar Intent；后者会把用户带到日历 App。事件实例接口用于按时间窗获取包括重复日程在内的实例。

**判断：**主线使用数据 API，不使用 `ACTION_INSERT` 编辑器。写入系统日历后重读 event ID，可以证明手机端结果存在，而不是只生成一段建议。

**边界：**必须预先授权，并选择可写日历。设备可能没有任何可写日历，模拟器亦可能没有日历 UI；首日须解决此先决条件。创建本地日历涉及按 sync-adapter 方式使用 `ACCOUNT_TYPE_LOCAL`，不能假设任意普通 calendar insert 都可用；首版优先已有日历。

### R4. 不需要把短能力调用变成前台服务

来源：[Android：启动前台服务](https://developer.android.com/develop/background-work/services/fgs/launch)

**事实：**前台服务有通知要求和启动限制；Android 12+ 对从后台启动有限制，Android 14+ 还检查相应服务类型权限。

**判断：**本任务不需要通过前台服务常驻等待模型。Provider 只处理有限操作，图片预先本地化，能减少通知与后台调度复杂度。若未来能力需要长时间手机计算，必须重新设计执行生命周期，不能无限占用一次 IPC。

### R5. 模拟器适合开发，不能自动替代真机

来源：[Android Emulator 官方说明](https://developer.android.com/studio/run/emulator)

**事实：**Emulator 在电脑模拟 Android；每个 AVD 实例有独立设备配置和私有用户数据。官方同时支持模拟器和物理设备测试。

**判断：**在 Linux/Windows 上用官方模拟器开发和演示本项目是合理选择。原题要求物理手机，与用户当前确定的模拟器交付范围有差异，应透明说明，不能声称已满足这一项。优先官方 AVD，避免初期把时间花在第三方模拟器的定制 ADB 或多显示设备兼容问题上。

## 3. scrcpy 与隐藏副屏：关键陷阱

### R6. 创建副屏不等于隔离焦点和输入法

来源：

- [scrcpy v4.1 虚拟显示文档](https://github.com/Genymobile/scrcpy/blob/v4.1/doc/virtual-display.md)
- [scrcpy v4.1 发布页](https://github.com/Genymobile/scrcpy/releases/tag/v4.1)
- [NewDisplayCapture.java](https://github.com/Genymobile/scrcpy/blob/v4.1/server/src/main/java/com/genymobile/scrcpy/video/NewDisplayCapture.java)

**事实：**本轮 GitHub release API 返回最新正式版为 v4.1，发布于 2026-07-12。文档原文：

> By default, the virtual display IME appears on the default display.

`--no-vd-system-decorations` 只关闭系统装饰/默认 launcher。v4.1 在 Android 14+ 设置 `OWN_FOCUS`，但没有设置 `STEAL_TOP_FOCUS_DISABLED`。`--no-vd-destroy-content` 会在关闭副屏时把内容移到主屏，不适合本题的默认策略。

**判断：**不能直接运行一条 `scrcpy --new-display` 就宣布无干扰并发成立。

### R7. OWN_FOCUS 与不抢 top focus 是不同条件

来源：

- [Android 14 DisplayManager flags](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/core/java/android/hardware/display/DisplayManager.java)
- [Android 14 VirtualDisplayAdapter](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/services/core/java/com/android/server/display/VirtualDisplayAdapter.java)
- [Android 14 Display.java](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/core/java/android/view/Display.java)

**事实：**Android 14 已有 `VIRTUAL_DISPLAY_FLAG_STEAL_TOP_FOCUS_DISABLED = 1 << 16`；需要同时具有 `TRUSTED` 和 `OWN_FOCUS`。转换后的 Display flag 是另一位值，不可混用。Display.java 说明启用后只有定向输入才能到达该显示设备，并写道：

> The framework only supports IME on the top focused display … implicitly disables showing any IME.

**判断：**值得实验的小改版 scrcpy 应设置上述组合，但必须接受副屏无 IME 的代价。它不是一种完整的第二手机桌面保证。

### R8. 普通 APK 与 shell 权限不同

来源：

- [AOSP Android 14 Shell manifest](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/packages/Shell/AndroidManifest.xml)
- [AOSP DisplayManagerService](https://github.com/aosp-mirror/platform_frameworks_base/blob/android15-release/services/core/java/com/android/server/display/DisplayManagerService.java)
- [AOSP WindowManagerService](https://github.com/aosp-mirror/platform_frameworks_base/blob/android15-release/services/core/java/com/android/server/wm/WindowManagerService.java)

**事实：**AOSP shell 声明 `ADD_TRUSTED_DISPLAY`、`INTERNAL_SYSTEM_WINDOW` 和 `INJECT_EVENTS` 等权限；创建可信副屏和修改 IME policy 有权限检查。

**判断：**无 root 的 shell 实验路线有源码依据；普通 APK 使用反射不会凭空获得系统权限。OEM 可能另外限制，不能把 AOSP 当作每台手机的测试结果。

### R9. LOCAL 策略和定向文本的能力有限

来源：

- [AOSP 多显示设备 IME 支持](https://source.android.com/docs/core/display/multi_display/ime-support)
- [scrcpy 键盘说明](https://github.com/Genymobile/scrcpy/blob/v4.1/doc/keyboard.md)
- [scrcpy 输入注入](https://github.com/Genymobile/scrcpy/blob/v4.1/server/src/main/java/com/genymobile/scrcpy/device/Device.java)
- [AOSP TextView](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/core/java/android/widget/TextView.java)

**事实：**官方说明系统使用单个 IME，随着焦点在显示设备之间转移。`local` 只改变显示位置。scrcpy SDK 文字输入基于 KeyEvents，支持范围有限；不等于任意 Unicode 的 `commitText`。TextView 的 `ACTION_SET_TEXT` 是直接设置文本的候选能力。

**判断：**主屏中文组合输入 + 副屏输入必须实测；先验证 ASCII。无障碍节点能否精确绑定副屏、目标 WebView/自绘控件是否支持直接文本设置，都是未解决兼容项。

### R10. 显示隔离不等于 App 实例隔离

来源：

- [AOSP 多显示设备 Activity 启动](https://source.android.com/docs/core/display/multi_display/activity-launch)
- [Android task 与启动模式](https://developer.android.com/guide/components/activities/tasks-and-back-stack#TaskLaunchModes)
- [AOSP multi-resume](https://source.android.com/docs/core/display/multi_display/multi-resume)

**事实：**指定启动 display 可能复用已有 task；`singleTask`、全局应用状态和外部 Intent 不会因为有副屏就自动隔离。scrcpy 的 `+package` 启动方式会 force-stop 整个包。

**判断：**第一轮只验证不同包，不支持主人与 Agent 任意同时操作同一个 App。同包、分享面板、权限页和登录页必须单独列兼容范围。

## 4. AutoGLM 和其他 GUI Agent 能复用什么

### R11. AutoGLM 是视觉决策与现有 GUI 执行框架

来源：

- [用户提供的智谱 AutoGLM-Phone 文档](https://docs.bigmodel.cn/cn/guide/models/vlm/autoglm-phone)
- [Open-AutoGLM 仓库](https://github.com/zai-org/Open-AutoGLM)
- [固定版本模型客户端](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/model/client.py)

**事实：**模型输入包括截图与任务，客户端解析 `do(action=...)` / `finish(message=...)` 等动作。模型 API 返回决策，客户端承担手机执行。仓库已经包含 iOS 适配，不能说 AutoGLM 完全不支持 iOS。

**判断：**可借鉴观察—决策—执行闭环；不能指望模型解决操作系统的焦点隔离问题。GUI 定位能力也不能直接证明它擅长车票、酒店和会议截图的结构提取。本项目现有模型的 vision 和结构化输出能力需单独探测。

### R12. 原执行器不能直接接到“无干扰”副屏

核验代码固定为 commit `86f55382982fb054e8fc98ca80609dff8a2cdc3c`：

- [screenshot.py](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/adb/screenshot.py)
- [device.py](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/adb/device.py)
- [input.py](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/adb/input.py)
- [handler.py](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/actions/handler.py)

| 通道 | 现有实现事实 | 并发风险 |
| --- | --- | --- |
| 截图 | `screencap` 未指定 display | 可能读取用户主屏 |
| tap / swipe / long press | `input` 未带 `-d` | 未绑定 Agent 副屏 |
| Home / Back | 无 display 约束的 keyevent | 主屏导航风险 |
| Launch | `monkey -p` | 未保证任务启动位置 |
| Type | 切换为 ADB Keyboard、清文本广播、输入广播、恢复 IME | 会影响全局默认输入法和当前焦点 |

`device_id` 是 ADB 设备序列号，不是 `display_id`。`Note` 和 `Call_API` 在已读执行器中只是占位成功返回；不能据动作名字认定已有记忆或系统 API 能力。

### R13. 相关项目作为参照，不作为并发证明

- [PhoneLLM Awesome 汇总](https://github.com/PhoneLLM/Awesome-LLM-Powered-Phone-GUI-Agents)：论文和系统入口，属于二手索引。
- [AppAgent](https://github.com/TencentQQGYLab/AppAgent)：可借鉴探索形成应用知识和简化动作空间。
- [AndroidWorld](https://github.com/google-research/android_world)：可借鉴模拟器上的参数化任务和终态验收。

这些项目的任务成功率或 App 覆盖数量，不能替代“主人在同一设备连续输入时不被干扰”的实验。

## 5. iOS：能做受限后台助手，不能承诺通用隐藏 GUI

### R14. WDA / XCUITest 不提供已核验的第二个交互桌面

来源：

- [Open-AutoGLM iOS 部署说明](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/docs/ios_setup/ios_setup.md)
- [iOS 执行器](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/actions/handler_ios.py)
- [Apple XCUIAutomation](https://developer.apple.com/documentation/xcuiautomation)
- [Apple XCUIApplication](https://developer.apple.com/documentation/xcuiautomation/xcuiapplication)

**事实：**这条部署路线要求 macOS/Xcode、签名和 iPhone 上的 WebDriverAgent。操作包括截屏、触摸、启动 App、回 Home，没有 Android 式的副屏 session。

**判断：**它能自动操作 iPhone，但与用户争用实际界面。没有 Mac 时可以考虑云 Mac/远程构建，但不能据此解除系统输入隔离限制。直接在 iPhone 上安装测试 App 也不意味着免掉构建、签名和调试工具链。

### R15. iOS 后台任务不能一概视为常驻执行器

来源与已读原文：

- [BGProcessingTask](https://developer.apple.com/documentation/backgroundtasks/bgprocessingtask)：
  > Processing tasks run only when the device is idle. The system terminates any background processing tasks running when the user starts using the device.
- [iOS 26 BGContinuedProcessingTaskRequest](https://developer.apple.com/documentation/backgroundtasks/bgcontinuedprocessingtaskrequest)：由前台用户动作触发，再延续到后台。
- [BGContinuedProcessingTask](https://developer.apple.com/documentation/backgroundtasks/bgcontinuedprocessingtask)：
  > The system displays the progress of this task in a Live Activity.
- [长时间运行任务指南](https://developer.apple.com/documentation/backgroundtasks/performing-long-running-tasks-on-ios-and-ipados)：存在系统调度、取消、资源和进度报告要求。
- [延长后台执行时间](https://developer.apple.com/documentation/uikit/extending-your-app-s-background-execution-time)：`beginBackgroundTask` 只能请求有限额外时间，需要处理 expiration；没有固定 30 秒保证。
- [后台 URLSession](https://developer.apple.com/documentation/foundation/downloading-files-in-the-background)：后台传输可在应用挂起时由另一进程继续，但有调度和唤醒限流，不等于任意代码持续运行。

**判断：**普通 BGProcessing 不适合“用户一直在用”的核心场景；iOS 26 连续任务较接近，但系统可见进度与严格零 Agent 画面要求可能冲突。短后台任务能试受限 demo，仍需验证实际完成时限，不能保证 1–2 分钟内任意多轮任务。

### R16. iOS 语义接口有可行空间

来源：

- [AppIntent supportedModes](https://developer.apple.com/documentation/appintents/appintent/supportedmodes)
- [EventKit 权限](https://developer.apple.com/documentation/eventkit/accessing-the-event-store)
- [创建事件和提醒](https://developer.apple.com/documentation/eventkit/creating-events-and-reminders)
- [PhotoKit 授权范围](https://developer.apple.com/documentation/photokit/delivering-an-enhanced-privacy-experience-in-your-photos-app)
- [Apple 快捷指令指南](https://support.apple.com/guide/shortcuts/welcome/ios)

**事实：**App Intent 可公开自己 App 的动作，其中允许后台模式的动作可后台执行。EventKit 可以在预授权后直接保存事件/提醒；若日历需要写后读回，write-only 权限不够。快捷指令存在自动化与网络请求能力，不能笼统判为不可用。

**判断：**iOS 可做“预先选择图片→请求模型→保存系统日历/提醒”的限定助手；每个动作是否拉前台、是否有确认、是否能在后台完成都要测。仅调用云端接口完成事情，也不能证明手机端执行能力。

## 6. 证据质量与未验证项

本轮成功获取了用户给出的三项参考资料，以及上文涉及的 Android / Apple 正文和关键源码。Apple 的普通 HTML 常是 JS 外壳，正文通过官方 `developer.apple.com/tutorials/data/documentation/...json` 获取；对外引用规范页面 URL。

部分网络请求发生 SSL EOF，采用重试、GitHub contents API 或正确仓库路径补齐。scrcpy 的正确路径是 `doc/virtual-display.md`。Android 选图文档本轮未成功抓取，因此设计不据此宣称已验证持久化 Photo Picker 行为，首版明确在准备阶段复制授权文件。运行中的 AOSP main 分支和网页可能变化；实现时应固定 commit、SDK 和工具版本。

目前只确认 `.env` 中存在模型配置变量，未输出其值，也未调用模型 API。以下均仍未验证：Provider 实际 UID/权限、模拟器启动、日历可写性、截图提取正确率、任务时延、性能影响；真机并发和 GUI 副屏 flag 在 OEM 上的行为也未知。[验证计划](../validation/2026-09-21-feasibility-and-demo.md)区分首版必过门槛和可选真机/GUI 验证，不能从调研结论直接改写为产品能力。
