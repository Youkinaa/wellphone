# 同一 AVD 的副屏并发探针

这是设计前置实验，验证 Appium 是否能在主屏持续输入期间操作副屏原生控件；不是 Agent 或业务演示。主屏由脚本点击合成 IME 的按钮，不能当作真人拼音输入。实验记录、结果边界见[验证报告](../../docs/validation/2026-09-21-appium-concurrency-probe.md)。

只在无私人数据的专用 AVD 上运行：脚本会安装准备好的控制程序、创建/销毁副屏、启动测试页面、点击主屏测试键盘，并记录两边的合成文本及系统元数据。Appium/scrcpy 原始端口仅供本机实验器使用，尚无产品级设备端守卫。

## 1. 构建

需要 Python 3、Node 24、JDK 21、Android SDK platform 36 / build-tools 36.0.0，以及一个 API 34 AVD。SDK/AVD 安装按 Android 官方工具完成；报告记录了本次实际镜像，不能只凭 API 号认为任意镜像结果相同。

从仓库根目录运行；路径变量须替换成实际本地目录：

```sh
export WELLPHONE_PROBE_SDK_ROOT=/path/to/android-sdk
export WELLPHONE_PROBE_JDK_HOME=/path/to/jdk-21
./experiments/display_concurrency/fixtures/build.sh
./experiments/display_concurrency/build_flags.sh
```

取得 scrcpy v4.1（commit `49c9501fb26f456bbf4a341dd68879f670c67452`）的干净源码，在其根目录应用本目录的 `steal-top-focus-disabled.patch`。保留原上游许可证；本仓库不复制完整第三方源码。

```sh
# 在 scrcpy 源码根目录，PATCH_PATH 是本仓库补丁的绝对路径。
patch -p1 < "$PATCH_PATH"
cd server
env JAVA_HOME="$WELLPHONE_PROBE_JDK_HOME" \
  PATH="$WELLPHONE_PROBE_JDK_HOME/bin:$PATH" \
  ANDROID_HOME="$WELLPHONE_PROBE_SDK_ROOT" \
  ANDROID_PLATFORM=36 ANDROID_BUILD_TOOLS=36.0.0 \
  BUILD_DIR="$SCRCPY_BUILD_DIR" bash ./build_without_gradle.sh
```

`SCRCPY_BUILD_DIR` 设为已创建的输出目录绝对路径。该补丁仅增加禁抢 top focus 的显示标志；不包含计划中的消息白名单、Toast、文本尾缀或设备端绑定补丁。

Appium 使用本地 npm 项目，锁定并核对实际安装树：Appium 3.7.0、UiAutomator2 driver 8.7.0、server 10.6.6、android-driver 14.2.0。只写顶层版本不能锁定传递依赖；本次运行版本与构建产物哈希见报告。

## 2. 准备专用 AVD

启动单个 API 34 AVD，记下实际 serial；以下 `adb` 应来自上述 SDK。固定 720×1280、density 240，预装三份夹具和旗标读取器：

```sh
adb -s "$PROBE_SERIAL" shell wm size 720x1280
adb -s "$PROBE_SERIAL" shell wm density 240
adb -s "$PROBE_SERIAL" install experiments/display_concurrency/fixtures/out/probe-main.apk
adb -s "$PROBE_SERIAL" install experiments/display_concurrency/fixtures/out/probe-agent.apk
adb -s "$PROBE_SERIAL" install experiments/display_concurrency/fixtures/out/probe-ime.apk
adb -s "$PROBE_SERIAL" push experiments/display_concurrency/out/display-flags.jar /data/local/tmp/wellphone-display-flags.jar
adb -s "$PROBE_SERIAL" shell settings get secure default_input_method
adb -s "$PROBE_SERIAL" shell ime enable com.wellphone.probe.ime/.ProbeIme
adb -s "$PROBE_SERIAL" shell ime set com.wellphone.probe.ime/.ProbeIme
adb -s "$PROBE_SERIAL" shell am start --display 0 -n com.wellphone.probe.main/com.wellphone.probe.ProbeActivity
adb -s "$PROBE_SERIAL" shell input -d 0 tap 360 327
```

记录原 IME ID，结束后恢复。IME 的切换只发生在实验准备/清理期，不属于并发输入手段。安装到不同签名的旧夹具上会失败；用新专用 AVD 或明确清理旧测试包，不对业务 App 做处理。

确认主屏只显示 main 夹具，编辑框为空或仅含此前夹具生成的字符、光标在末尾、没有未提交的 composing，且编辑框有焦点、ProbeIME 可见。坐标固定：`ni=(180,1015)`、`nihao=(540,1015)`、`你好=(180,1090)`、`A=(540,1090)`、IME snapshot=`(540,1170)`，页面 READBACK=`(360,471)`。分辨率、导航布局或键盘不同就需要重新测量；不盲发这些坐标。

Appium 准备安装 instrumentation 也仅在专用实验环境执行。其会话可与普通输入并存，但不能同时启动第二个 UiAutomation，包括 `uiautomator dump`。

## 3. 运行与读结果

在已安装上述依赖的 npm 项目启动 host server：

```sh
env ANDROID_HOME="$WELLPHONE_PROBE_SDK_ROOT" JAVA_HOME="$WELLPHONE_PROBE_JDK_HOME" \
  ./node_modules/.bin/appium --address 127.0.0.1 --port 54723
```

回本仓库，在另一个终端运行：

```sh
python3 experiments/display_concurrency/run_probe.py \
  --adb "$WELLPHONE_PROBE_SDK_ROOT/platform-tools/adb" \
  --serial "$PROBE_SERIAL" --appium-url http://127.0.0.1:54723 \
  --scrcpy-server "$SCRCPY_BUILD_DIR/scrcpy-server" \
  --output /path/to/new-local-run-directory --seconds 60
```

脚本保留一个未提交的 composing span，创建副屏并执行一次 Appium 文本写入；随后运行 60 秒主屏输入基线、60 秒主屏输入与副屏 source/find/replace/readback/定向点击并发，最后采一条默认 idle=10000 的 source 对照。每键验证主屏真实文本、选区、composing 和 IME 成功事件；检查全程实例、焦点及输入会话是否变化。

`summary.json`、`events.jsonl`、筛选后的夹具日志、XML、dumpsys 和副屏 H264 都留在输出目录。数值显示 flags 必须满足 `(flags & 0x1880) == 0x1880` 且 `(flags & 4) == 0`；Android 14 的 dumpsys 名称列表漏打印两项，不能按其字符串断言缺失。

`runner_completed=true` 只表示这份机制实验的脚本检查通过。还需复核系统焦点采样、实际视频解码及主副屏事件交错，不能替代真人/真实 App/异常边界验收。raw H264 无可靠墙钟时间戳，ffprobe 猜测的播放时长不等于实验时长。

`python3 experiments/display_concurrency/analyze_results.py /path/to/run-directory` 从已完成记录重新汇总连续性、HTTP 延迟和系统采样；它不操作设备，也不自动给出产品验收结论。协议格式自检：`python3 -m unittest discover -s experiments/display_concurrency -p 'test_probe_protocol.py'`。

结束时脚本删除它创建的 Appium session，关闭副屏及自己的 scrcpy ADB 转发；原 IME 由操作者恢复，host server 和 AVD 也由操作者关闭。未覆盖滑动、Back/Enter、特殊文本尾缀、旋转、旧句柄、断连、真实 App 跳转与帧卡顿指标；参照完整验证计划逐项补验。
