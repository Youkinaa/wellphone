# 真实 App 安装与登录准备

日期：2026-09-21。美团和腾讯会议已安装，并分别打开首次隐私/服务协议页面；本轮自动化准备未代用户接受协议、登录或创建会议/订单。**安装/首次启动通过，不等于登录、业务页面或副屏并发兼容通过。** 用户在准备期自行登录，随后再做真实页面预检。

## 1. AVD 与本次镜像调整

AVD 是 Android Virtual Device，即模拟器使用的一台虚拟 Android 设备的配置与数据。项目运行时仍是**一个 AVD、同一 Android 实例、主副两块显示区域**；这次保留旧实验配置、另建 App 测试配置，先关闭旧实例才启动新实例，不用两个独立设备冒充同机并发。

| 项目 | 本次 App 准备环境 |
| --- | --- |
| AVD 名称 / serial | `wellphone_api34_apps` / `emulator-5580` |
| 系统镜像 | Google APIs Android 14 / API 34 / x86_64 / revision 14，无 Play Store |
| fingerprint | `google/sdk_gphone64_x86_64/emu64xa:14/UE1A.230829.050/12077443:userdebug/dev-keys` |
| 实际 ABI / native bridge | `x86_64,arm64-v8a` / `libndk_translation.so` |
| 显示 / CPU / RAM | 720×1280，density 240；2 核、3072 MiB，SwiftShader |
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

## 3. 在当前电脑打开并登录

模拟器窗口运行于工作区所在 Linux 桌面 `DISPLAY=:1`。它不在用户自己的 iPhone 上，也不会自动出现在 SSH/VS Code 的本地桌面。能访问此 Linux 图形桌面时，使用模拟器窗口即可；仅 SSH 访问时仍需配置可用的远程桌面入口，当前未部署远程访问服务。

关闭后可在这台电脑的图形桌面终端重新启动（已有进程时不要重复启动）：

```sh
env ANDROID_AVD_HOME="$HOME/.cache/wellphone/avd" \
  ANDROID_HOME="$HOME/.cache/wellphone/android-sdk" \
  "$HOME/.cache/wellphone/android-sdk/emulator/emulator" \
  -avd wellphone_api34_apps -port 5580 -no-snapshot -no-audio \
  -no-boot-anim -no-metrics -gpu swiftshader -memory 3072 -cores 2 -skin 720x1280
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

后续依照[验证计划](2026-09-21-feasibility-and-demo.md)推进：用户登录 → 真实 App 必要页面预检 → 副屏填写/转移与主屏真人输入并发 → 通用 Agent。问题与最终解决过程持续更新[开发日志 J07](../development-journal.md)。
