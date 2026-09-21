# Wellphone

用户在 Android 主屏刷屏、打字，Agent 在**同一个 Android 实例的虚拟副屏**操作真实 App。**已通过原生控件与合成 IME 的并发机制探针；通用 Agent、真人输入和真实 App 尚未验收。** 开发与演示以单个官方 Android 模拟器为主，真机可选。

候选方案：LangGraph 通用编排 + LangChain 消息/模型适配 + 可修改的任务 DAG + 外置 skills + Appium/scrcpy 受控 GUI 工具。计划演示行程截图转日历（VLM 直接识别）、查询/创建腾讯会议、按需求点外卖；三者共用执行器，通过真实 App 界面完成，不接业务 API。**先做无需 LLM 的副屏与真实 App 预检，通过后再实现 Agent 内核。**

```mermaid
flowchart LR
    U[用户] --> MAIN[AVD 主屏]
    C[Web 上传 / 对话 / 计划审阅] --> G[LangGraph + 任务 DAG]
    S[外置 skills] --> G
    G <--> L[LangChain / 模型 API]
    G <--> R[Redis 历史 / SQLite 执行状态]
    G --> T[受控适配层 / Appium / scrcpy]
    T <--> SUB[同一 AVD 副屏的真实 App]
```

**计划部署步骤**（实现后补充可执行命令）：

1. 安装 Android Studio / SDK / Platform Tools，首轮固定一个 API 34 AVD；准备主屏使用 App、日历、一个外卖 App 和腾讯会议，预先登录。截图拟通过 Web 上传，VLM 读原图，业务写入仍走手机 GUI。
2. 准备固定版本 Appium UiAutomator2 与 scrcpy，应用必要的显示隔离补丁；验证副屏观察/中文填写及主屏持续输入，配置见主设计。
3. 启动带持久化的本地 Redis；配置模型与设备参数，启动电脑 Agent 和控制台。SQLite 状态与截图保存在本地。
4. 运行通用 Agent，查看 DAG、动作和证据；从真实 App 列表重新打开结果核验。下单与支付按具体授权执行并分别报告状态。

| 环境变量 | 用途 / 状态 |
| --- | --- |
| `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LLM_MODEL` | 已有模型配置；图像输入、结构化输出和 GUI 定位待验证 |
| `REDIS_URL` | 拟定：会话历史连接地址 |
| `ANDROID_SERIAL` | 拟定：唯一目标 AVD；副屏 ID 由会话管理器分配 |
| `WELLPHONE_STATE_DIR`、`WELLPHONE_SKILLS_DIR` | 拟定：本地状态/证据目录与产品技能目录 |

上述新增配置名尚未接入代码。`.env`、截图、账号数据和原始轨迹不入库；产品 `skills/` 与开发助手的 `.agents/skills/` 分开。

- [主设计](docs/superpowers/specs/2026-09-21-wellphone-design.md) · [运行时契约](docs/superpowers/specs/2026-09-21-agent-runtime-contracts.md) · [状态与时序](docs/superpowers/specs/2026-09-21-execution-flows.md)：模块输入输出、DAG/replan、澄清/授权/接管；[开发规范](AGENTS.md)规定同步维护。
- [交互应用设计](docs/superpowers/specs/2026-09-21-interaction-app-design.md)：Web 上传、对话、任务控制、SSE 恢复；设计基线，尚未实现。
- [本轮资料核验](docs/research/2026-09-21-agent-runtime-and-gui-research.md) · [平台研究与历史路线](docs/research/2026-09-21-platform-research.md)：三份用户参考及官方源码依据。
- [验证与演示计划](docs/validation/2026-09-21-feasibility-and-demo.md)：实验门槛、三个演示、7 天安排和未通过时的处理。
- [原 AOSP 实测报告](docs/validation/2026-09-21-appium-concurrency-probe.md) · [探针部署步骤](experiments/display_concurrency/README.md)：60 秒主屏合成输入期间，副屏完成 141 轮操作；保留限制与失败记录。
- [App 准备与性能排查](docs/validation/2026-09-21-real-app-preparation.md)：用户已确认美团、腾讯会议登录；机制复验完成 87 轮，真实页面待验收。
- [开发问题与决策日志](docs/development-journal.md)：持续记录问题、证据、取舍、修复结果和面试复盘。

范围：单用户、单进程、单 AVD、单副屏、单活动任务；只承诺通过实测的 App/页面。模拟器验证不等于原题的物理手机部署，该项有设备后补验。
