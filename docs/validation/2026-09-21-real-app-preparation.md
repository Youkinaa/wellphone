# 真实 App 安装与登录准备

日期：2026-09-21。**用户已明确反馈美团和腾讯会议登录成功。** 首次安装时自动化只打开隐私/服务协议页，之后由用户完成登录，未代用户创建会议或订单。安装、用户确认登录与真实业务/副屏并发验收分别记录，后两项页面验收仍未完成。

## 1. AVD 与本次镜像调整

AVD 是 Android Virtual Device，即模拟器使用的一台虚拟 Android 设备的配置与数据。项目运行时仍是**一个 AVD、同一 Android 实例、主副两块显示区域**；这次保留旧实验配置、另建 App 测试配置，先关闭旧实例才启动新实例，不用两个独立设备冒充同机并发。

| 项目 | 本次 App 准备环境 |
| --- | --- |
| AVD 名称 / serial | `wellphone_api34_apps` / `emulator-5580` |
| 系统镜像 | Google APIs Android 14 / API 34 / x86_64 / revision 14，无 Play Store |
| fingerprint | `google/sdk_gphone64_x86_64/emu64xa:14/UE1A.230829.050/12077443:userdebug/dev-keys` |
| 实际 ABI / native bridge | `x86_64,arm64-v8a` / `libndk_translation.so` |
| 显示 / CPU / RAM | 720×1280，density 240；**4 核、6144 MiB，host / NVIDIA 硬件渲染**（同日升级，兼容问题见 3.3） |
| 工具 | Emulator 37.1.11、ADB 37.0.1；未使用 `adb root` |

官方镜像来源：[仓库元数据](https://dl.google.com/android/repository/sys-img/google_apis/sys-img2-3.xml)、[r14 下载](https://dl.google.com/android/repository/sys-img/google_apis/x86_64-34_r14.zip)。下载大小 `1563721130` 字节，SHA1 `e0f6c9a0691aa27bd597d0deb1bcfdc943ac8ca7`，与官方元数据匹配，已解压校验。

原 `wellphone_api34_probe` 使用 AOSP 镜像，设备仅报告 `x86_64` 且 `native.bridge=0`。安装官方美团包时明确失败：

```text
INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract native libraries, res=-113
```

官网包为 ARM64 原生库，不能直接安装到该镜像。新镜像的 ARM64 翻译解决了此次安装障碍；两个 `adb install` 均返回 `Success`。未更改 APK、绕过登录或改用仿真 App。原镜像和[原并发证据](2026-09-21-appium-concurrency-probe.md)保留，新镜像须有自己的验证记录。

## 2. 官方 APK 与核验

| 项目 | 美团 | 腾讯会议 |
| --- | --- | --- |
| 包名 | `com.sankuai.meituan` | `com.tencent.wemeet.app` |
| 版本 / versionCode | 12.66.202 / 1200660202 | 3.46.0.477 / 2024061631 |
| minSDK / targetSDK | 21 / 30 | 21 / 35 |
| 原生 ABI | arm64-v8a | arm64-v8a、armeabi-v7a |
| APK 字节数 | 91083078 | 273060134 |
| 核验 | ZIP CRC、APK v1/v2 签名验证通过 | ZIP CRC、APK v1/v2 签名验证通过，官方 MD5 一致 |
| 首次启动 | `am start -W` 返回 `Status: ok`，截图确认中文协议弹窗 | `am start -W` 返回 `Status: ok`，截图确认英文协议弹窗 |

下载链路均从官网页面及其脚本核对，不使用第三方 APK 镜像：

- 美团：[官网](https://www.meituan.com/mobile/) → [下载入口](https://dd.meituan.com/appupdate/download/simple/group/64?channel=meituan) → [官方 APK](https://v.meituan.net/mobile/app/Android/group-1200660202__aarch64_0-meituan.apk/meituan)。
- 腾讯会议：[官网](https://meeting.tencent.com/download/) → 官网 `query-download-info` 下载元数据 → [官方 APK](https://updatecdn.meeting.qq.com/cos/d5dd4c1f5e50a2f72faf2245da393666/TencentMeeting_0300000000_3.46.0.477.publish.officialwebsite.apk)。这里查询的是安装包元数据，没有调用会议业务 API。

```text
美团 APK SHA256:
23b7049baf9d1ea99c46cbe7cc8c8b96bbfe5db2dc5ff24b02715c904629c6fe
美团签名证书 SHA256:
73a611c3a01dc6e11388873daeee1e556ad9e5768e5c222055f508a24c3a8215
腾讯会议 APK SHA256:
cda13249c176a5bb93f66306751cb1770672dad6af7492fbf301a51be67029fa
腾讯会议签名证书 SHA256:
695b5657e6bdb44c0b09d19292d6d67e08cf7c4ffecdb9e72cf6618d768c4691
腾讯会议官方 MD5:
d5dd4c1f5e50a2f72faf2245da393666
```

签名验证证明下载的 APK 签名完整性；来源由官网链路确认，没有把新记录的证书指纹称为已与独立历史信任库比对。原文件与核验元数据保存在本机 `~/.cache/wellphone/app-downloads/`，不提交 APK。

### 2.1 用户追加安装 QQ

同日按用户要求，在同一 `wellphone_api34_apps` 安装普通 Android QQ：包名 `com.tencent.mobileqq`，版本 **9.3.65 / 16240**，minSDK 23、targetSDK 34，原生 ABI 为 `arm64-v8a`。设备安装返回 `Success`，回读包版本与 ABI 一致；启动 `com.tencent.mobileqq.activity.SplashActivity` 返回 `Status: ok`，随后观察到 QQ 登录 Activity。未代用户填写账号或发送消息，未将 QQ 新增为 Agent 已验收业务。

来源：[QQ 官网](https://im.qq.com/index/) → 官网下载脚本/移动端配置 → [官方下载包](https://downv6.qq.com/qqweb/QQ_1/android_apk/9.3.65_2a98ecf55b5ee03a.apk)。APK 为 `392021727` 字节，ZIP CRC 与 v1/v2/v3 签名验证通过，无签名警告。本地文件为 `~/.cache/wellphone/app-downloads/qq-official.apk`，来源与核验元数据为同目录 `qq-official-evidence.json`。

```text
QQ APK SHA256:
f63ecbac6980d2109a7ceb854db0324668b1318cf50c884c0e7c35752cffef84
QQ 签名证书 SHA256:
ea6e97ad6c34f7039a9c6daba732c97d0e098e83ede2b4d52c76eb0184ac7a38
```

## 3. 在当前电脑打开并登录

模拟器窗口运行于工作区所在 Linux 桌面 `DISPLAY=:1`。它不在用户自己的 iPhone 上，也不会自动出现在 SSH/VS Code 的本地桌面。能访问此 Linux 图形桌面时，使用模拟器窗口即可；仅 SSH 访问时仍需配置可用的远程桌面入口，当前未部署远程访问服务。

关闭后可在这台电脑的图形桌面终端重新启动（已有进程时不要重复启动）：

```sh
env ANDROID_AVD_HOME="$HOME/.cache/wellphone/avd" \
  ANDROID_HOME="$HOME/.cache/wellphone/android-sdk" \
  "$HOME/.cache/wellphone/android-sdk/emulator/emulator" \
  -avd wellphone_api34_apps -port 5580 -no-snapshot -no-audio \
  -no-boot-anim -no-metrics -gpu host -memory 6144 -cores 4 -skin 720x1280
```

在应用列表打开“美团”与“Tencent Meeting”，由用户处理首次协议、登录和验证码；确认美团已保存地址、腾讯会议可进入账号首页。当前模拟器默认为英文界面；语言、日历时区和通知设置在后续准备期明确，不能在正式并发任务中偷偷改全局配置。`-no-audio` 是本次准备环境的宿主音频配置，不是证明产品不会产生声音干扰的测试手段。

必要时可从终端打开登录入口，**只用于用户知情的准备期主屏操作**：

```sh
"$HOME/.cache/wellphone/android-sdk/platform-tools/adb" -s emulator-5580 shell am start -W \
  -n com.sankuai.meituan/com.meituan.android.pt.homepage.activity.MainActivity
"$HOME/.cache/wellphone/android-sdk/platform-tools/adb" -s emulator-5580 shell am start -W \
  -n com.tencent.wemeet.app/com.tencent.wemeet.app.StartupActivity
```

登录数据留在 AVD 本地 userdata；`-no-snapshot` 不清除 userdata。不要 `-wipe-data`、卸载 App 或把 AVD 数据加入 Git。用户无需把密码/验证码写入聊天或仓库。后续调试先记录包名、必要页面和脱敏结果，再检查副屏启动、控件树、中文填写与页面跳转。

### 3.1 回桌面与导航排查

用户反馈按返回/主页后 App 仍在前台。本次检查时系统初始化已完成，未启用锁定任务，默认桌面和系统 Home 路径可用；美团登录 Activity 则有一次明确的 `am_anr` 事件，原因是触摸派发等待超过 5001 ms。不能由此认定所有按键失败均由同一个问题导致，也不能把安装成功写成页面运行稳定。

在用户请求排查的准备期，将导航从手势模式改为三键模式（`navigation_mode: 2 → 0`），已确认底部显示 **◀ 返回、● 主页、■ 最近任务**。返回用于退一层页面；主页用于回桌面且保留 App 后台状态；最近任务用于查看/切换任务，划走卡片不等于强制停止所有后台服务。

从美团发送一次系统 Home 后，5 次前台采样均为桌面。切换三键后，从 QQ 点击底部主页，前 3 次采样为桌面，第 4 次采样暂未返回 top-resumed Activity，随后页面继续变化；连续 4 次均为桌面的断言未通过，未将这次检查记为稳定性测试通过。已停止自动点击，用户侧按键体验待确认；美团 ANR 根因和稳定性仍未解决，见[开发日志 J08](../development-journal.md)。

本报告第 4 节的 87 轮机制实验发生在切换导航之前；之后若复跑固定坐标探针，必须重新核对导航/键盘布局和坐标。此次准备期导航调整不作为 Agent 执行期间修改主屏设置的许可。

### 3.2 登录后美团卡顿：配置取证与 GPU 对照

本节记录升级前的历史实验；当前配置与后续结果以 3.3 为准。

用户反馈登录成功但美团很卡。先只读采样，随后在用户明确“暂时不用，可以留给调试”的窗口尝试一次图形配置对照；不清除 userdata、不卸载或重新登录、不创建订单。下列是准备期主屏检查，**不是主副屏并发性能验收**。

| 检查 | 2026-09-21 实际证据 | 可得结论 |
| --- | --- | --- |
| 宿主加速能力 | i7-11700K、16 线程、约 31 GiB RAM；RTX 3070 Ti 8 GiB / 驱动 565.57.01；DISPLAY=:1 的 GLX direct rendering=Yes | 有可用硬件图形加速，不是宿主没有独显 |
| CPU 虚拟化 | `emulator -accel-check` 返回 KVM usable；运行进程持有 KVM VM/vCPU fd | 没有把整个 x86 Android 放在纯软件 CPU 模拟里 |
| 原配置 | 2 vCPU / 3072 MiB / `-gpu swiftshader`；启动日志实际为 Google SwiftShader | 图形仍由 CPU 软件渲染，ARM64 App 原生代码另有翻译成本 |
| 宿主内存短采样 | `vmstat 1 6` 的 5 个区间 `si=so=0`，memory pressure avg10=0 | 这几秒未见宿主正在交换；已用 swap 不等于当前换页瓶颈 |
| 模拟器内存 | 一次可用约 434 MiB；后续 8.03 秒为约 520→517 MiB，swap 已用约 1.87 GiB；增量换入 10 页、换出 0 页 | 余量偏小，但这段样本没有持续换页证据；不能只凭剩余内存定根因 |
| 累计美团帧统计 | 初次 1961 帧 / 24.17% jank；后续 2246 帧 / 21.99%，p95=97 ms | App 确有卡顿记录；是进程累计动态统计，不能当成固定时长基线或 Agent 干扰率 |

受控动作是在美团首页预热 4 次滚动、重置该 App 的 `gfxinfo`，再执行相同的 24 次上下滚动。每次动作前检查前台仍为美团首页；未做点击购买或更改账号。

| 阶段 | 结果 |
| --- | --- |
| 原 SwiftShader 的当前已运行环境 | 24 次完成，15.52 秒；486 帧、34 卡顿帧（7.00%），p95=24 ms、p99=30 ms |
| 同 AVD 改为 `-gpu host`，核数/内存/尺寸不变 | 重启完成，日志和 SurfaceFlinger 确认 NVIDIA GLES 生效；美团首次启动 `Status: ok` |
| host 下相同滚动 | 一次 ADB swipe 等待超过 25 秒；系统 13:31:27 记录首页 `MainActivity` 输入等待 5003 ms 的 ANR，画面出现 “Meituan isn't responding”；未取得完整的对照帧样本，判该轮失败 |

host 启动还记录 `Vulkan driver doesn't support any external memory modes`，但 GLES 和界面均能初始化；它与此次美团 ANR 的因果关系未定。匹配的 App ANR trace 未提供可用 main 线程栈，不能把同份 DropBox 中的 system_server 栈当作美团栈。旧软件渲染环境已有登录页 ANR，故既不能宣称换 GPU 修好了，也不能单凭这一次断言所有卡顿由 host 模式引起。

这不是严格控制所有变量的 GPU 基准：重启改变进程/缓存/后台服务，首页内容依赖网络。当前结论仅是“软件渲染配置存在可优化空间；直接切 host 的本轮运行未通过”。已回退原 SwiftShader 配置，未同时加内存/核数来掩盖失败。

**回退与恢复记录：**第一次回退启动成功，随后模拟器进程退出 139，回退滚动探针在第一条状态查询即因 ADB 离线终止，未获得帧样本。宿主 Apport 在 13:37:44 确认 qemu PID 3892909 的 signal 11，内核前一秒记录 RenderThread segfault；因程序不属于系统软件包，Apport 未保存可解析 core。再次按原参数启动后，`sys.boot_completed=1`，ADB 在线，SurfaceFlinger 回读 Google SwiftShader，前台为 NexusLauncher，三键模式 0、原 Google IME 均保留。未清除 userdata；短时恢复不等于模拟器崩溃或美团 ANR 已修复，未完成回退滚动复验，也未继续真实 App 副屏检查。宿主崩溃与 App ANR 分开追踪，见[开发日志 J10](../development-journal.md#2026-09-21--j10回退时发生宿主模拟器崩溃)。

本地证据：`artifacts/diagnostics/2026-09-21-meituan-readonly.json`、`meituan-swiftshader-scroll.json`、`meituan-host-scroll-failed.json`、两份启动日志及脱敏 ANR 摘要，均默认不入库。后续针对 ANR 做线程/原生桥与负载分析，CPU、RAM、GPU 各自单变量验证；没有实测就不承诺参数加大后一定流畅。官方说明：[图形与 VM 加速](https://developer.android.com/studio/run/emulator-acceleration)、[ARM 应用翻译](https://android-developers.googleblog.com/2020/03/run-arm-apps-on-android-emulator.html)。

### 3.3 用户要求升级资源：4 核 / 6 GiB 与新的失败证据

本节是 3.2 历史对照之后的新一轮配置升级；**旧 2 核/3 GiB 和 87 轮机制证据不代表新配置已验收**。宿主短采样可用内存约 8.84 GiB、CPU 空闲约 63–65%，换掉原 3 GiB 实例后选择 4 vCPU / 6 GiB，给宿主和后续运行时留余量。CPU/RAM/GPU 同时升级属于用户要求的容量调整，不能据此推导单个参数的性能收益。

持久修改本地 AVD `config.ini` 为 `hw.cpu.ncore=4`、`hw.ramSize=6144`、`hw.gpu.enabled=yes`、`hw.gpu.mode=host`；原配置保留为 `config.before-resource-upgrade-20260921-135546.ini`。未清除 userdata、卸载 App 或更改账号。实际 guest `cpu/online=0-3`，MemTotal 为 6074336 KiB（扣除系统保留），SurfaceFlinger 报 NVIDIA GeForce RTX 3070 Ti；不是只改了文档或启动参数。

| 顺序 | 检查与结果 | 解释边界 |
| --- | --- | --- |
| 4 核/6 GiB/host 首次启动 | 系统启动完成；美团启动返回 ok、TotalTime 1222 ms，但约 17 秒后崩溃回桌面 | `am start` 成功不能证明 App 持续可用 |
| 14:02:28 美团原生崩溃 | `preload-general` 线程 SIGABRT，`Bad JNI_OnLoad`；Java 栈为自带 MTWebView `13800109` 初始化 → System.loadLibrary，native 栈进入 `libndk_translation::DoBadTrampoline` | 定位到 MTWebView 原生库加载的 ARM 翻译/JNI 边界；缺具体 so 地址映射，不能认定翻译器自身 bug、GPU 根因或与 ANR 同因 |
| 同配置重新打开美团 | 返回 ok、TotalTime 647 ms，截图确认首页；滚动探针在预热阶段 ADB swipe 超过 25 秒，14:06:40 记录 MainActivity 等待 5005 ms 的 ANR | 没完成 24 次测量，没有新卡顿率或“更流畅”的证据 |
| 仅回退渲染为 SwiftShader，保留 4 核/6 GiB | 系统启动完成、美团启动 ok（2053 ms）；14:09:56 宿主 QEMU 再次 signal 11，进程退出 139，ADB 消失 | 与 3.2 中低资源 SwiftShader 的宿主崩溃均有记录；没有可用 core，仍不能断言具体渲染函数或与 App 崩溃同因 |
| 恢复最终调试配置 | 回到 4 核/6 GiB/host；回读 boot=1、CPU 0–3、NVIDIA GLES、NexusLauncher、三键导航和原 Google IME，不再自动打开美团 | 选择能维持本轮系统启动的配置供后续定位；不标记 App 或持续稳定性通过 |

最终仍用本页第 3 节启动命令。两种渲染均未取得美团稳定业务证据，不能把参数加大当作修复，也不再堆新参数试错。下一步围绕上述 MTWebView/JNI 触发链和 ANR 分别取线程/库映射证据，必要时讨论固定 App/镜像/模拟器版本；不私自替换登录环境或扩大为新平台迁移。

脱敏结果保存在本地 `artifacts/diagnostics/meituan-upgraded-host-failed.json`；首轮定向 logcat、崩溃摘要、各次启动日志和 Apport 记录留作未解决问题证据，不入 Git。新配置尚未跑主副屏真人输入或业务验收。问题与状态见开发日志 J11–J12。

## 4. 验证边界与后续工作

换镜像后已用同一探针源码重新运行，结果见[本镜像机器记录](../../experiments/display_concurrency/results/2026-09-21-google-api34.json)，不直接沿用原 AOSP 的 141 轮结论：

| 测量 | 本镜像结果 |
| --- | --- |
| 主屏单独输入基线 | 60.61 秒，83 轮合成输入 |
| 并发阶段 | 60.30 秒，主屏 69 轮 / 276 次逐键检查；副屏 87 轮读树、中文替换、读回、定向点击 |
| 交错证据 | 按宿主接收时间统计：87 次副屏读回全部落在完整主屏输入周期内；69 个周期中的 68 个包含副屏读回，不是同步设备/HTTP 时钟测量 |
| 焦点与输入连接 | 2706 条主屏/IME 事件无连续性违例；68 次系统采样的 top display 和 IME display 均为 0，client 不变 |
| 副屏范围 | 本次动态分配 display 2，flags `0x1f88`；89 份 XML 未含主屏包标记 |
| 取树耗时 | idle=0 的 87 次中位数 208.28 ms；默认 idle 的一次对照 10107.45 ms |
| 视频 | 副屏 H264，720×1280，975 帧完整解码，ffmpeg 退出 0 且无错误输出 |

上述仍是**标准原生夹具 + 自制合成 IME**，不是人用拼音输入，也不是 App 业务验收。当前夹具 APK 的哈希与原轮不同，已分别核对本轮构建记录、本地文件及设备安装包一致；记录了本轮实际哈希，未改写旧证据。主屏合成输入吞吐比本轮基线降低约 16.4%，未测帧卡顿，不宣称“完全不卡”；镜像、App 安装和宿主窗口条件改变，不能把两轮差异单独归因于 ARM 翻译。原版 Appium 的启动 Toast、特殊文本尾缀与设备端守卫尚未补齐，G1/G2 仍未整体验收。

原始证据在本机 `/tmp/wellphone-concurrency-run/google-api34-run-001/`，关键文件 SHA256 已入机器记录。探针结束后已关闭 Appium host/会话和副屏，恢复 Google 普通输入法并禁用 ProbeIME，模拟器保留在桌面供用户登录。没有持续录制登录过程。

本轮尚未验证美团搜索/结算、腾讯会议查询/预约、后台旧 task、支付/外链或通知干扰。语义快照与模型编排仍为设计阶段。

后续依照[验证计划](2026-09-21-feasibility-and-demo.md)推进：登录已由用户确认 → 性能诊断及真实 App 必要页面预检 → 副屏填写/转移与主屏真人输入并发 → 通用 Agent。交互层可按设计基线并行开发，不依赖所有业务页面均通过；真实任务执行入口仍受设备门槛控制。问题与最终解决过程持续更新[开发日志](../development-journal.md)。
