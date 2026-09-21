# 原生副屏并发实验夹具

这是同一 Android 实例双 display 实验的最小夹具，不是产品实现。两个独立包与进程提供原生 `EditText`、计数按钮及读回；第三个包提供固定字符的合成 IME。仅输入合成测试文本，编辑框内容会记录到 `WellphoneProbe` 日志。夹具不读取其他 App 文本，不提供网络、广播或 Intent 参数控制接口。

| 输出 APK | 包名 | 启动组件 / IME ID |
| --- | --- | --- |
| `out/probe-main.apk` | `com.wellphone.probe.main` | `com.wellphone.probe.main/com.wellphone.probe.ProbeActivity` |
| `out/probe-agent.apk` | `com.wellphone.probe.agent` | `com.wellphone.probe.agent/com.wellphone.probe.ProbeActivity` |
| `out/probe-ime.apk` | `com.wellphone.probe.ime` | `com.wellphone.probe.ime/.ProbeIme` |

## 构建

需要 Android SDK platform 36、build-tools 36.0.0、JDK 21、Bash 与 Python 3；APK target SDK 为 34，最低为 26。以下命令仅本地构建，不连接或安装到设备：

```sh
WELLPHONE_PROBE_SDK_ROOT=/path/to/android-sdk \
WELLPHONE_PROBE_JDK_HOME=/path/to/jdk-21 \
./build.sh
```

也可用 `--sdk-root PATH --jdk-home PATH` 覆盖环境变量。`WELLPHONE_PROBE_PLATFORM` / `--platform` 和 `WELLPHONE_PROBE_BUILD_TOOLS` / `--build-tools` 可指定工具版本。脚本直接调用 aapt2、javac、d8、zipalign 和 apksigner，不依赖 Gradle。构建后验证签名与对齐，并将 APK、包元数据、SHA-256 和临时实验签名材料放在已忽略的 `out/`；这些文件不提交。

## 控件与证据

编辑框 ID 为 `<包名>:id/probe_editor`，保留原生无障碍 `ACTION_SET_TEXT` 行为。其他 ID：`probe_show_ime`、`probe_counter`、`probe_readback`、`probe_state`。agent 的 `probe_set_sample` 仅做本地样本自检，不能充当外部 SET_TEXT 成功证据。

`WellphoneProbe` 记录实例/进程/display、文本、选区、composing 范围、窗口/编辑框焦点、输入连接创建次数及 IME 可见性；焦点与选区回调即时记录，稳定 composing 状态另以 100 ms 采样。`WellphoneProbeIME` 记录输入会话与输入视图的开始/结束计数，以及各个固定字符操作的返回值。

合成 IME 仅由界面按钮调用 `setComposingText("ni"/"nihao", 1)`、`commitText("你好"/"A", 1)` 和 `finishComposingText()`；拒绝向两个夹具包之外的目标写入。实验应逐步验证主屏 composing/选区、会话连续性和副屏写入读回，同时检查系统焦点元数据。只有最终文字正确不能排除中途断连；采样也不能排除全部瞬时变化。

该夹具只能验证原生 `EditText` 与合成 Android 输入连接路径，不能代表真实拼音候选词输入、真实 App 兼容性、真实用户持续操作或完整产品已通过。设备安装、IME 选择/恢复、display 创建和运行实验由上层实验入口负责。
