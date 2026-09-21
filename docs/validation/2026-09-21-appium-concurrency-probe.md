# Appium 与主屏输入并发：前置机制实验

日期：2026-09-21。问题：Appium 能否在用户使用主屏时继续读取副屏控件并填写中文，而不是等主屏停止操作？

**结论：指定 Android 14 AVD、带禁抢焦点补丁的 scrcpy、明确配置的 Appium，在原生控件与合成 IME 条件下通过了连续并发实验。原版 Appium 单独开箱即用仍不满足完整设计要求。** 这是 P2 的机制子实验，不将 G1/G2/G3 标为全部通过；没有真人输入、真实拼音输入法或三个业务 App 的验收结果。

本轮没有读取模型凭据、调用模型/业务 API 或使用真实账号。只实现可复现探针，没有开始通用 Agent/业务 skills。源码与运行步骤见[实验入口](../../experiments/display_concurrency/README.md)，数值、版本及哈希见[机器可读记录](../../experiments/display_concurrency/results/2026-09-21-api34.json)。

后续为兼容官网 ARM64 APK 改用 Google APIs API 34 镜像；安装与该镜像的独立复验见[真实 App 准备报告](2026-09-21-real-app-preparation.md)。本报告保留原 AOSP 运行条件和结果，不代表所有 API 34 镜像。

## 1. 实验对象与实际版本

| 对象 | 实际使用 |
| --- | --- |
| Android | 单个 AOSP x86_64 API 34 AVD，serial `emulator-5580` |
| Build fingerprint | `Android/sdk_phone64_x86_64/emu64x:14/UE1A.230829.036.A1/11228894:userdebug/test-keys` |
| 官方系统镜像归档 | `https://dl.google.com/android/repository/sys-img/android/x86_64-34_r04.zip`；内部 package revision 为 2，以 fingerprint 识别实际构建 |
| Emulator / platform-tools | 37.1.11 / 37.0.1；Linux x86_64，KVM，AVD 2 核 / 2048 MiB，软件 GPU |
| 主屏 / 副屏 | 同一实例，720×1280、density 240；最终运行 display 0 / 5，ID 从运行结果取得 |
| scrcpy | v4.1，commit `49c9501fb26f456bbf4a341dd68879f670c67452`；仅新增 `STEAL_TOP_FOCUS_DISABLED` |
| Appium / Node | 3.7.0 / 24.20.0 |
| UiAutomator2 driver / server / AndroidX | 8.7.0 / 10.6.6 / 2.3.0 |
| appium-android-driver | **14.2.0**；此前资料核验的是 14.0.8，不能将其误写成实际安装版本；重新核对了已安装版本的 IME 初始化路径 |
| 构建 | 本地 JDK 21.0.7，SDK platform 36，build-tools 36.0.0；夹具 target 34 |

scrcpy server SHA-256：`a16e9d26e6b132c6885e851eeb8e9c9a25588fa6c7b3b26904b396cb9bc56c68`。完整 APK 哈希和探针源码哈希在机器记录中；本地重新签名的夹具 APK 不保证二进制哈希相同。

两边是不同包的原生 `EditText`：`com.wellphone.probe.main` 与 `com.wellphone.probe.agent`。主屏使用自制 ProbeIME，通过 Android `InputConnection` 的真实 composing/commit 方法输入固定字符；脚本通过 `adb input -d 0 tap` 点击该键盘。这模拟输入连接的并发行为，**不是人操作，也不是完整拼音候选词引擎**。

## 2. 验证如何执行

1. 在准备期选择 ProbeIME，让主屏编辑框保持焦点。运行中不切输入法、不用全局剪贴板，也不启动第二个 UiAutomation。
2. 在主屏保留尚未提交的 `ni` composing span；创建 scrcpy 副屏、启动副屏夹具、建立一个 Appium session，定位副屏字段并执行中文/emoji 替换和读回，再核对主屏组合范围与 IME 会话。
3. 先测约 60 秒主屏基线：反复 `ni → nihao → 提交“你好” → 提交“A”`，每键核对文本、选区、composing 和 IME 返回值。Appium 会话存在，但不发副屏命令。
4. 再测约 60 秒并发：主屏保持同一输入循环；副屏反复 `source → find → replaceElementValue → fresh find → text readback → scrcpy 定向点击计数按钮`。
5. 保持主屏输入，单独把 idle 恢复到 10000，测一次 source；随后恢复 0。此对照只有一个样本，不作为完整性能基准。
6. 用夹具回调日志检查全区间的实例、焦点和输入连接；每约 2 秒采集系统 window/IME 元数据，独立重算结果，解码副屏视频。没有主屏连续视频或帧卡顿采样。

显示数值为 `0x1f88`，满足必要位 `TRUSTED | OWN_FOCUS | STEAL_TOP_FOCUS_DISABLED = 0x1880`，且 PRIVATE 位 `0x4` 未设置。不要混用 VirtualDisplay 的请求 mask `0x1fdcb` 与最终 Display flags。

Appium 实际采用 `autoLaunch=false`、`noReset=true`、`skipUnlock=true`、`skipDeviceInitialization=true`、`skipLogcatCapture=true`、`disableSuppressAccessibilityService=true`；省略 `hideKeyboard` 和 Unicode 键盘能力。`newCommandTimeout=180` 仅管理会话无命令时的存活时间。绑定后回读 `currentDisplayId=5`、`enableMultiWindows=true`、`waitForIdleTimeout=0`、`enableNotificationListener=false`。

本实验使用**原版 Appium server**，没有完成从启动禁 Toast、特殊文本尾缀去除全局 Enter、设备端 display/epoch 守卫。实验设置关闭监听后等待缓存过期再读树，不能据此宣称启动期间没有采集主屏内容；当前全部是合成测试数据。

## 3. 实测结果：run-003

| 检查 | 实测 |
| --- | --- |
| 主屏无副屏动作基线 | 60.63 秒，87 轮完整输入循环 |
| 主副屏并发 | 60.65 秒，主屏 79 轮 / 316 次逐键验证；副屏 141 轮完整观察、中文替换、准确读回与定向点击 |
| 是否等主屏停手 | 141 次副屏读回都位于主屏输入循环期间；79 个主屏循环每个都有副屏读回事件（宿主接收时间基准） |
| 主屏文字 / composing | 各步与最终字符串准确；启动期间持有的组合范围未改变 |
| 主屏焦点 / 输入连接 | `window_focus_lost` 始终 0；`input_connections` 始终 1；main/IME 进程和实例不变 |
| IME 生命周期 | start/finish 计数从 2/1 到 2/1，输入视图计数从 1/0 到 1/0；初始计数来自准备阶段，运行中没有增加 |
| 独立日志核对 | 跨 setup、基线、并发、对照及阶段间边界的 2946 条 main/IME 事件，没有上述连续性违例 |
| 系统采样 | 69 组：top focused display 始终 0；同一 main IME client，IME token display 始终 0 |
| 副屏 XML | 143 份（setup 1、并发 141、idle 对照 1），没有 main 包标记；不代替启动 Toast 隔离验收 |
| 副屏视频 | H264 720×1280，974 帧，完整解码无错误/警告；抽帧看到中文内容变化与 COUNT 141 |

副屏 HTTP 延迟（同一次运行、毫秒，包含本机 HTTP/ADB/server 路径）：

| 操作 | 样本数 | 中位数 | 最大值 |
| --- | --- | --- | --- |
| source，idle=0 | 141 | 120.72 | 292.65 |
| find，idle=0 | 282 | 49.87 | 177.29 |
| replace，idle=0 | 141 | 66.45 | 155.87 |
| text readback，idle=0 | 141 | 22.09 | 109.33 |
| source，idle=10000 | 1 | 10104.64 | 10104.64 |

默认全局等待确实在持续主屏活动下造成了约 10 秒延迟。关闭它后，仍通过 fresh node 和读回校验状态；不能把 `waitForIdleTimeout=0` 理解为不需要等待目标控件就绪。

主屏循环由基线 87 轮变为并发 79 轮，**没有把它隐去，也没有把它当成帧卡顿率**：该循环包含 ADB 往返、日志读取和逐步断言，共享资源开销会影响吞吐。未采 FrameTimeline/Perfetto，不能声称“完全不卡”已通过。系统采样可能漏瞬时变化，回调日志也不代表穷尽所有实际设备/控件行为。

原始 H264 没有墙钟时间戳，ffmpeg 补出的播放时长不是 60 秒并发证据；并发时长来自实验事件的单调时钟。原始轨迹保留在本地 `/tmp/wellphone-concurrency-run/run-003/`，不提交大段日志；仓库保存汇总和原始文件哈希。

## 4. 前两次中止与修正

保留失败记录，不只展示最后一轮：

- **run-001：探针误判显示标志。** 依赖 `DisplayInfo.toString()` 出现焦点标志名称的断言失败，Appium 尚未启动。实际 `DisplayDeviceInfo` 已含这些标志。核对 [Android 14 DisplayInfo.flagsToString](https://github.com/aosp-mirror/platform_frameworks_base/blob/android-14.0.0_r1/core/java/android/view/DisplayInfo.java#L936)发现打印器省略两项；改成读取运行时数值并严格检查必要位，未降低要求，也没有把它误报成镜像不支持。
- **run-002：Appium 默认会话空闲期限与实验冲突。** 主屏保持 composing 时的副屏写入已通过，60.44 秒基线完成 87 轮；随后 Appium 日志明确报告 `New Command Timeout of 60 seconds expired`，并发完成 0 轮。显式设置 `newCommandTimeout=180` 覆盖实验基线，未增加 HTTP/动作等待。正式 Agent 同样要管理等待模型/用户时的会话生命周期。

修正后用仓库的参数化探针重新执行完整 60 秒 + 60 秒实验，run-003 退出码 0。协议单元检查 4 项通过；原生 APK、scrcpy server、数值旗标读取器均完成实际构建。独立审阅分别重算了输入/焦点证据和解码了副屏视频。

实验结束已恢复原 LatinIME、禁用 ProbeIME，移除临时设备旗标读取器，关闭本次 Appium host 与专用 AVD；SDK、AVD 和源代码保留供后续真实页面预检。当前没有后台运行的实验会话。

## 5. 选型影响与下一道门槛

**保留 Appium + scrcpy 方案，有了运行证据；不把 stock Appium 直接开放给 Agent。** 这次证明的是同机输入机制可以并存，不是任意 App 自动获得了浏览器 context 一样的隔离。

| 已有证据 | 仍须先于上层 Agent 完成 |
| --- | --- |
| 定向副屏、标准控件中文与主屏合成 composing 可并行 | 真人持续输入、真实拼音候选词选择与屏幕/键盘完整录像 |
| 当前副屏可读树、可定位、可读回文本 | 真实日历/图库、腾讯会议、外卖关键页面及 WebView/自绘控件预检 |
| 正确 flags 和稳定主屏 IME | 旧 task/同包竞争、登录/保存/支付/外链跳转、异常重连、旋转、Back/Enter/滑动 |
| 当前工具配置克服全局 idle 等待 | 完成设备端显示世代守卫、启动禁 Toast、文本特殊尾缀与控制消息约束 |
| 文字和焦点指标正确 | 主屏卡顿、宿主窗口焦点、通知/声音/振动指标 |

下一步是用这个底座验证真实 App 的必要路径，并补正式隔离边界；这些可以独立于 LangGraph、Redis 和 LLM 完成。某个 App 不通过就记录具体页面/控件/版本，不在完整业务写完之后才重新选型。完整标准继续以[验证计划 G0–G6](2026-09-21-feasibility-and-demo.md)为准。
