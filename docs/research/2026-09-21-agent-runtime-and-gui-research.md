# V2 研究：通用编排、外置技能与真实 App 副屏操作

核验日期：2026-09-21。方法：实际获取官方网页、官方 Doc/源码和项目实现；不是只阅读项目简介。初稿为资料研究，随后补做了[同机并发机制实验](../validation/2026-09-21-appium-concurrency-probe.md)：**指定 AVD 的原生控件/合成 IME 路径通过；没有真人输入、真实业务 App、模型/业务 API 或真实任务结果。** 下文按来源区分资料事实、设计决定和设备证据。

## 结论与证据边界

这三份参考分别提供设备控制底座、视觉操作决策和 Agent 方法索引，没有一份已核验材料直接给出本项目完整的“用户主屏持续中文输入、Agent 同机副屏完成真实业务”验收结果。不能直接拼接原执行器；也不能据此断言世界上不存在其他实现。

| 问题 | 本轮可以明确作出的判断 | 还需要什么证据 |
| --- | --- | --- |
| 同一 Android 能否建立独立交互副屏 | 可以，scrcpy 与 AOSP 已有创建、取帧及定向输入机制；指定 AVD 的原生控件探针已运行 | 真实 App 的兼容和完整隔离验收 |
| 主副屏能否各使用一套普通软键盘 | 本方案核验的普通同用户 Android 14 路径不支持；单 IME 随最高焦点切换 | 不继续把“双 IME”当候选方案 |
| 副屏无 IME 时能否写中文 | 标准可编辑 TextView 的 SET_TEXT 接收 CharSequence，直接修改内容；无需用拼音键盘模拟中文 | 真实控件暴露该动作且页面正确响应 |
| SET_TEXT 的焦点请求是否必然抢主屏 | 不必然；系统调用链及原生控件并发实验均支持这一判断，见 2.3 和实测报告 | 真人拼音及真实 App 无额外跨屏行为的集成实验 |
| 目标 App 所有必要页面是否留副屏 | 有默认同屏启动规则，但已有 task、显式指定显示等可改变落点 | 无需 LLM 的真实页面预检，见 2.4 |

选型结论：**“有明确系统实现依据的候选方案”，尚不是“目标 App 全部跑通的产品能力”。** 先完成[无 LLM 预检](../validation/2026-09-21-feasibility-and-demo.md)，再开发完整 Agent。

## 1. 用户给出的三份参考：读到了什么、用在哪里

| 参考 | 本轮阅读范围 | 具体用于本项目的结论 |
| --- | --- | --- |
| [scrcpy](https://github.com/Genymobile/scrcpy) | v4.1 虚拟显示/键盘文档、NewDisplayCapture、Controller；结合 Android 14 显示和焦点源码 | 复用副屏创建、取帧、定向输入；修改并验证不抢 top focus 的 flag；不宣称原版直接隔离 |
| [AutoGLM-Phone](https://docs.bigmodel.cn/cn/guide/models/vlm/autoglm-phone) | 官方模型说明、Open-AutoGLM 动作提示、解析器、执行器和输入实现 | 借鉴截图→下一步动作；复用模型适配思想，替换默认 ADB 执行层；模型不决定 display 和权限 |
| [Phone GUI Agents 汇总](https://github.com/PhoneLLM/Awesome-LLM-Powered-Phone-GUI-Agents) | 重读索引，并跟进 AppAgent、AppAgentX、AutoDroid、Mobile-Agent-E 的文档和代码 | 借鉴 UI 经验、提示/快捷动作、反思与结果核验的分层；不把论文成功率当作并发隔离证据 |

### 1.1 scrcpy 的能力和缺口

事实：v4.1 建屏已有 PUBLIC，按 Android 版本加 TRUSTED/OWN_FOCUS，但未加 `STEAL_TOP_FOCUS_DISABLED`。Controller 对新屏的定向事件使用其 display ID，尚未知新屏时拒绝注入；应保留这种失败即拒绝的行为。

官方文档原文：

> By default, the virtual display IME appears on the default display.

`--display-ime-policy=local` 只改变键盘显示位置；`--no-vd-system-decorations` 只影响装饰/launcher；`--no-vd-destroy-content` 会在关闭时将内容移到主屏。不能把这些开关等同多输入者隔离。

来源：[虚拟显示](https://github.com/Genymobile/scrcpy/blob/v4.1/doc/virtual-display.md)、[建屏源码](https://github.com/Genymobile/scrcpy/blob/v4.1/server/src/main/java/com/genymobile/scrcpy/video/NewDisplayCapture.java)、[Controller](https://github.com/Genymobile/scrcpy/blob/v4.1/server/src/main/java/com/genymobile/scrcpy/control/Controller.java)、[键盘说明](https://github.com/Genymobile/scrcpy/blob/v4.1/doc/keyboard.md)。

决定：底座固定版本后做小范围 server 修改，不继承主屏控制通道。scrcpy 提供传输和输入基础，规划、权限、skills、业务核验由本项目补齐。正式会话也关闭[剪贴板自动同步](https://github.com/Genymobile/scrcpy/blob/v4.1/server/src/main/java/com/genymobile/scrcpy/control/Controller.java#L146)，禁止相关控制消息；[back-or-screen-on](https://github.com/Genymobile/scrcpy/blob/v4.1/server/src/main/java/com/genymobile/scrcpy/control/Controller.java#L658)在屏灭时会发 POWER，因此 Back 采用独立定向 KEYCODE_BACK，不能直接继承该复合动作。

补查相关社区讨论：[UHID 显示关联 PR #6009](https://github.com/Genymobile/scrcpy/pull/6009)明确区分独立鼠标指针与键盘限制，但原 PR 未合并，其表述也仅限该 UHID 方案；现行 v4.1 能力以 Controller 源码为准。[多用户启动 #6858](https://github.com/Genymobile/scrcpy/issues/6858)与[应用分身请求 #5848](https://github.com/Genymobile/scrcpy/issues/5848)是需求讨论，不能作为已支持同包隔离的证据。

### 1.2 AutoGLM 适合放在 GUI 执行决策层

事实：动作协议包括 `do(action="Tap", element=[x,y])`、Type、Swipe、Launch、Back、Wait、Take_over、finish；坐标约定为 0..999，现有执行器按 `/1000 * width` 换算。协议没有受信副屏身份，AST 解析也不能替代动作权限检查。

`Note` 和 `Call_API` 在核验执行器中是占位实现。原 Android 执行通道未完整指定 display，Type 会切换全局 ADB Keyboard。Tap 是否弹确认的一部分信息来自模型，不能单凭模型自报判断影响。详细通道审计保留在[首轮 R11–R12](2026-09-21-platform-research.md)。

来源：[提示词](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/config/prompts_zh.py)、[动作执行器](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/actions/handler.py)、[文字输入](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/adb/input.py)。本轮也重抓 main 关键文件复核上述行为。

决定：保留 PlannerModel / GuiModel 的接口分工，MVP 可用同一已配置模型承担两种角色；仅在能力/延迟测试证明需要时分开。不能假设 `LLM_MODEL` 支持图片、结构化规划或 GUI 定位，首日探测。GUI 模型生成的动作统一转换成受控工具 schema，不执行模型生成代码。

### 1.3 从汇总中追读的实际实现

[PhoneLLM Awesome](https://github.com/PhoneLLM/Awesome-LLM-Powered-Phone-GUI-Agents) 是分类整理的论文、项目和评测资源索引，不是可安装的手机驱动、MCP 服务或完整 Agent。它帮助找到可比较的方法和可继续阅读的实现；本项目借鉴了下列思路，尚未集成这些项目代码，也不能用索引或论文成绩证明主副屏隔离。

| 项目与源码 | 核验事实 | 采用与舍弃 |
| --- | --- | --- |
| [AppAgent document_generation](https://github.com/TencentQQGYLab/AppAgent/blob/main/scripts/document_generation.py)、[executor](https://github.com/TencentQQGYLab/AppAgent/blob/main/scripts/task_executor.py) | 根据演示/探索的前后观察生成元素说明，执行时检索当前 UI 元素知识 | 外置 UI 经验可跨任务复用；知识需审阅，元素 ID 不能当作永久稳定定位 |
| [AppAgentX chain_evolve](https://github.com/Westlake-AGI-Lab/AppAgentX/blob/main/chain_evolve.py)、[deployment](https://github.com/Westlake-AGI-Lab/AppAgentX/blob/main/deployment.py) | 实际使用 LangGraph；高层动作含 preconditions、element_sequence、template_pattern，并有 fallback/完成检查 | 借鉴知识与通用执行分层；不引入其 Neo4j/Pinecone 等重型依赖 |
| [AutoDroid TaskPolicy](https://github.com/MobileLLM/AutoDroid/blob/newbranch/droidbot/input_policy.py) | 把任务相关元素经验注入当前 UI 状态；README 明确指出完成判断仍不可靠 | 可见元素范围约束和状态历史有价值；必须补独立终态核验 |
| [Mobile-Agent-E agents.py](https://github.com/X-PLUG/MobileAgent/blob/main/Mobile-Agent-E/MobileAgentE/agents.py) | 分 Manager/Operator/Reflector；Tips 是文本经验，Shortcuts 含前置条件及原子动作序列 | 借鉴外置 skills 与反思；不无条件重放长点击串，不继承全局 IME 输入 |

AppAgentX 本轮仓库树版本为 `d0fcaeb1f9a1f784192dac596e319a8004a5dec2`。实际集成时仍须固定所借鉴代码的 commit 与许可，不把当前文档 URL 当作依赖锁定。

## 2. 副屏窗口树与中文：比首轮发现更严格的边界

### 2.1 观测必须按 display 取窗口

Android API 30+ 有 `AccessibilityService.getWindowsOnAllDisplays()`；需要服务声明 `canRetrieveWindowContent`，设置 `FLAG_RETRIEVE_INTERACTIVE_WINDOWS`。取绑定 display 对应的 windows，再逐个 `getRoot()`，并交叉核对 `getDisplayId()`。

源码明确 `getRootInActiveWindow()` 的来源可以是任意逻辑显示设备，不能直接作为副屏观察。截图使用 scrcpy 绑定副屏帧；Android 也有 `takeScreenshot(displayId)`，不是必须同时实现两条截图通路。

来源：[AccessibilityService](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/core/java/android/accessibilityservice/AccessibilityService.java)、[AccessibilityWindowInfo](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/core/java/android/view/accessibility/AccessibilityWindowInfo.java)。

### 2.2 隐藏副屏不等于 PRIVATE display

[AccessibilityManagerService.isValidDisplay](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/services/accessibility/java/com/android/server/accessibility/AccessibilityManagerService.java#L4581) 排除非系统持有的 PRIVATE 虚拟屏。scrcpy 默认 PUBLIC 有观察基础；“隐藏”只表示不占用户主屏，不能为了隐藏把它改成 PRIVATE 后仍假设无障碍树可读。

### 2.3 焦点与中文已有明确系统契约，实测范围应收敛

官方 [IME 多显示文档](https://source.android.com/docs/core/display/multi_display/ime-support)明确写道：

> The system uses a single IME, but can shift between displays to follow user focus.

本次把 Android 14 焦点链路固定到 AOSP commit `6e47c7075b91983ae501114425ea25e6df7690c8`。以下是源码支持的机制结论，不把 Android 14 分支自动等同任意 OEM、后续版本或尚未安装的 AVD 镜像。

1. [Display.java](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/core/java/android/view/Display.java#L338)明确定义：`STEAL_TOP_FOCUS_DISABLED` 的 display 不抢其他屏的 top focus，只接收定向输入，并需配合 `OWN_FOCUS`；该组合隐式禁止副屏显示 IME。`local` 仅改变输入法位置，不产生第二套 IME。
2. [TextView 的 SET_TEXT](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/core/java/android/widget/TextView.java#L14315)读取 CharSequence，调用 `setText`/`setSelection`。对支持动作的标准可编辑控件，可以直接写中文，不需全局键盘或剪贴板。
3. 无障碍服务确实先请求窗口焦点，但该事实不等于必然抢主屏。显示上移路径检查 `canStealTopFocus()`；[DisplayWindowSettings](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/services/core/java/com/android/server/wm/DisplayWindowSettings.java#L292)又将禁抢标志映射为 `mDontMoveToTop`；[TaskDisplayArea](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/services/core/java/com/android/server/wm/TaskDisplayArea.java#L389)阻止 task 置顶把非 top 的副屏父容器一并抬到顶部。此前文档把后半条 task focus 路径列为未知，本次已补齐。
4. [WindowManagerService.hasInputMethodClientFocus](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/services/core/java/com/android/server/wm/WindowManagerService.java#L8010)检查客户端是否属于 top focused display；副屏不符合时返回拒绝。[InputMethodManagerService](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/services/core/java/com/android/server/inputmethod/InputMethodManagerService.java#L3763)在修改当前焦点窗口和切换 IME 连接之前返回，因此该普通输入请求路径不会把主屏 IME 连接切给副屏。

**机制判断：**主屏保持 top focus、副屏正确应用上述 flags、两边使用不同 App/任务、目标是支持 SET_TEXT 的标准控件且未发生额外跨屏行为时，“主屏保留 IME，副屏直接填写中文”有明确源码依据。不能继续把这一基础机制笼统标成完全未知。

**集成实验的范围：**核对实际镜像/flags；真实 App 的原生/WebView/自绘控件是否暴露且正确处理 SET_TEXT；页面回调是否额外启动其他 Activity；主屏组合输入期间是否出现版本相关行为或资源干扰。先用固定动作探针测试，不需要完整 Agent。若控件不支持，不能借 ADB Keyboard、全局剪贴板或业务 API 掩盖。

### 2.4 App 页面落点有规则，可以在写 Agent 前预检

[AOSP Activity launch policy](https://source.android.com/docs/core/display/multi_display/activity-launch)描述：通常从 Activity 启动的新 Activity 与调用者同屏；无显示关联的 shell/Application context 可能按最近交互/启动的显示设备选择；解析到已有实例时会受原 task 所在屏影响，显式指定显示还可能搬动既有实例。指定第一次启动的 display，不能因此认为后续所有页面都被隔离。

[`ActivityOptions.setLaunchDisplayId`](https://developer.android.com/reference/android/app/ActivityOptions#setLaunchDisplayId(int))提供启动目标，配合 [`isActivityStartAllowedOnDisplay`](https://developer.android.com/reference/android/app/ActivityManager#isActivityStartAllowedOnDisplay(android.content.Context,int,android.content.Intent))可做预检查，但不保证 App 自己后续产生的全部 Intent。`resizeableActivity` 是多窗口/尺寸适配信息，既不是“true 就全链留副屏”的充分条件，也不应把 false 直接当作“任何副屏全屏都不可运行”。

决定：先固定一个镜像与 APK 版本，用原版 scrcpy 人工走 App 必要页面，记录 task/display；再用补丁底座和 Appium 最小探针复验焦点/中文。首页、主流程、外部页面、已有 task、提交后页面分别记结果。未实际运行的支付链路不能被提交前检查替代。这样不必等 LangGraph、skills 或完整业务流程写完才发现 App 不兼容。

## 3. LangGraph：运行时循环与业务 DAG 分离

### 3.1 编排能力

[官方 Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) 明确支持循环和 super-step。编译后的图再添加节点不会改变已编译拓扑；[StateGraph 源码](https://github.com/langchain-ai/langgraph/blob/ed384f3a124660db6dccd6c53eaad48e1457e0b5/libs/langgraph/langgraph/graph/state.py)也有对应警告。

`Send` 是动态工作项到已注册节点的分发，不会自动提供业务依赖、资源锁、取消和 replan。`Command(goto=...)` 加入动态路由时，已有静态边仍可能执行，混用可能造成重复路径。

决定：固定通用 StateGraph，业务 DAG 存在 state；coordinator 校验/调度；目标级 agent_step 内有有界 GUI 循环。MVP 手机动作串行，只留并行离线计算扩展点。

### 3.2 修改状态与并发

[INVALID_CONCURRENT_GRAPH_UPDATE](https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE) 说明多个并行节点修改未定义 reducer 的同一 key 会冲突。reducer 可以合并数据，但不能替代业务冲突策略。[checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) 中 `update_state` 会产生新 checkpoint，也不是安全修改在途任务的万能按钮。

决定：请求进入持久控制事件队列；单一 run owner 在动作边界应用版本化 PlanPatch。worker 回报带 plan revision，旧结果不能覆盖新计划。

### 3.3 interrupt 和 replay 不保证业务幂等

[官方 Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) 原文：

> The node restarts from the beginning of the node where the interrupt was called when resumed.

checkpoint 可保存 super-step 和部分已完成写入，但从旧快照 replay 会重新执行后续模型/请求/节点。持久化不会把 Android 提交动作变成 exactly-once 事务。

决定：确认与执行分节点，操作账本保存稳定 operation ID；GUI 提交后超时先核对现实订单/会议，不重按按钮。正式版本的框架 API 和 timeout/durability 行为必须锁定版本后烟测，不能直接假设最新文档适配任意安装版本。

## 4. LangChain 消息与 Redis：避免两类常见误用

[官方 Messages](https://docs.langchain.com/oss/python/langchain/messages) 要求 `ToolMessage.tool_call_id` 对应 `AIMessage` 的工具调用 ID；`add_messages` 按消息 ID 合并。裁剪上下文时要保留完整工具调用组，不能只留下 tool result。完整消息编解码和历史摘要不是一回事。

| 后端选项 | 本轮源码核验 | 结论 |
| --- | --- | --- |
| `langchain_redis.RedisChatMessageHistory` | [源码](https://github.com/langchain-ai/langchain-redis/blob/fb667ca517542e4d04c591c6c908b63834170d78/libs/redis/langchain_redis/chat_message_history.py)初始化 JSON storage 的 SearchIndex | 不能认为任意无模块 Redis 都可直接使用 |
| community RedisChatMessageHistory | [源码](https://github.com/langchain-ai/langchain-community/blob/f425a3ed1933173fb3694b81359d1519c4f82d36/libs/community/langchain_community/chat_message_histories/redis.py)使用 LPUSH/LRANGE/EXPIRE/DEL | 普通 Redis 可参考，但仍需补 message ID 幂等和有界读取 |
| RedisSaver | [维护者 README](https://github.com/redis-developer/langgraph-redis/blob/32de20776e4dd4128b2c9eeafeea9742dc7a819b/README.md)明确 JSON/Search 依赖 | 可将来统一后端，本版不为它额外引入搜索模块 |
| AsyncSqliteSaver | [官方源码](https://github.com/langchain-ai/langgraph/blob/ed384f3a124660db6dccd6c53eaad48e1457e0b5/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/aio.py)面向轻量本地使用，提示生产写入限制 | 适合本版单进程单用户实验，不宣称生产扩展能力 |

决定：Redis conversation history + SQLite checkpoint/业务账本 + 文件 artifacts，提供可替换接口。历史和 checkpoint 职责分开，投递用稳定事件 ID 去重。MVP 不做多租户，不引入向量数据库。

## 5. 腾讯会议与外卖：为什么 GUI 是当前合理路线

### 5.1 普通腾讯会议账号可以通过 GUI 预约

[腾讯会议官方：预定常规会议](https://cloud.tencent.com/document/product/1095/53422) 明确支持免费等账号以及 Android/iOS，描述 App 中“预定会议→常规会议→完成”，完成后在会议列表中查看。勾选添加日历会打开日历，因此首轮关闭该选项，减少非请求的跨 App 跳转。

查询范围限定为当前账号在 GUI 中可见的会议；不把输入任意会议号并加入当作无副作用查询。不入会、不请求音视频；链接只在可见时读取，不借共享剪贴板取链接作为硬前提。

API 对照研究：[REST 前提条件](https://cloud.tencent.com/document/product/1095/42407)存在套餐和应用身份条件；[客户端 SDK](https://cloud.tencent.com/document/product/1095/58217)另有企业版条件；[成为开发者](https://cloud.tencent.com/document/product/1095/84322)又提供免费组织开发调试入口。正确结论是“普通账号不等于已有业务 API 权限”，而不是“个人绝无开发入口”。本版已选 GUI，不再依赖这些开通条件。

### 5.2 公开外卖接口不能默认作为消费者下单接口

本轮读取的[美团外卖合作页](https://developer.meituan.com/isv/waimai)和[开发概述](https://developer.meituan.com/docs/biz/comm-dev-summary)主要面向服务商、门店、菜品管理和商家接单。[饿了么餐饮入口](https://open.shop.ele.me/)当前为淘宝闪购服务商平台；[另一个开放入口](https://open.ele.me/)为蜂鸟配送，配送单并不等于消费者购物下单。

这些证据不能支持“这个个人账号可直接调用搜索商家→加购→下单 API”。没有穷尽所有商业合作能力，不断言接口绝不存在。GUI 路线使用用户现有登录和地址，不逆向私有接口或提取 cookie。

### 5.3 模拟器兼容仍是未知

商业 App 的 APK ABI、模拟器登录、验证码、定位、WebView 输入、支付跳转、同包任务复用均未测试。先固定一个外卖 App 和版本，避免首周适配多家。

外卖终态至少区分：准备完成未提交、已创建待支付、已支付待商家确认、结果未知。某个“提交”按钮可能同时创建订单并扣款，要根据实际页面和账户设置分类；不假设付款必然是另一个按钮。

## 6. 证据质量及下一步

已成功阅读三份用户参考和上述关键官方/开源内容。部分网页为 JS 页面，补读官网直接引用的公开资源；部分 raw 请求 TLS 失败后经重试或 GitHub API 获取。旧版/猜测路径的 404 与无关重定向未用于技术结论。

本轮不公开原始账号数据，不读取 `.env` 的值，不进行真实业务动作。实现时固定 SDK、scrcpy、模型适配库及 App 版本，并保留可复现实验记录。下一步最关键的证据是：**同一个 AVD 中主屏持续中文输入，副屏能完成真实 App 的观察、中文填写和保存，且无首次跳屏。**

## 7. 复用手机自动化框架与 MCP

针对“是否有手机版 Playwright/MCP”补充核验：**有，可以复用。** 进一步核查当前实现后，改选 Appium UiAutomator2 + scrcpy + 薄适配层；先前默认自写整套 Accessibility 桥的投入没有必要。设备驱动负责控件和输入，MCP 负责工具暴露与调用，副屏隔离和业务授权仍需项目约束。

### 7.1 可用框架与本项目取舍

| 方案 | 已有能力 | 本题需要补齐的边界 | 取舍 |
| --- | --- | --- | --- |
| Appium UiAutomator2 | 原生 App 的树/定位/文本/手势；当前版本已有 `currentDisplayId`、设备端窗口筛选和定向启动 | 默认树、Toast、key/Back、会话启动与失败回退不能直接继承 | 主选；复用定位/文本/启动，与 scrcpy 分工 |
| Python uiautomator2 | Python 调用树/控件/点击/文本；截图可传 `display_id`，当前底层 jar 也有多屏节点能力 | Python selector/click 未贯通可信 display 约束；dump 可含多屏，`send_keys` 有剪贴板/IME 路径 | 备用，不与 Appium 并行维护两套驱动 |
| Playwright Android | 实验性 Android API；Chrome/WebView 外，也有原生 selector 的 fill/click/swipe/tree | 原生公开 selector/input 没有本项目需要的完整 display 绑定；不是普通浏览器 context 隔离 | 不作为首版手机后端；不能误称只支持网页 |
| Playwright MCP | 浏览器导航、快照、点击等工具 | `--device/--mobile` 是浏览器移动设备模拟，不等于控制 AVD 原生 App | 不用于这三项原生 App 业务 |
| Mobile Next Mobile MCP | 原子截图、树/ref、点击、输入、启动、按键等，也有 batch | 工具选 device，默认 mobilecli 通路未按副屏隔离；核对的中文路径使用全局剪贴板 | 可借鉴工具接口，不直接使用默认执行器 |
| Maestro MCP | 官方 `maestro mcp`；inspect_screen、take_screenshot、run YAML | 工具选 device_id，Android RPC 未传 displayId；Unicode 临时切全局 IME | 适合常规测试流程；不直接用于主屏中文并发 |

Playwright 来源：[官方 Android API](https://playwright.dev/docs/api/class-android)、[AndroidDevice](https://playwright.dev/docs/api/class-androiddevice)、[Playwright MCP](https://github.com/microsoft/playwright-mcp)。本次源码固定 Playwright `07f1a6154795f055f341b8972086533e8e48b36f`，[原生 fill](https://github.com/microsoft/playwright/blob/07f1a6154795f055f341b8972086533e8e48b36f/packages/playwright-core/src/server/android/driver/app/src/androidTest/java/com/microsoft/playwright/androiddriver/InstrumentedTest.java#L164)实际委托 UiObject2.setText；这证明可复用自动化存在，不证明它已实现同机输入隔离。MCP README 仅核验当日 main，未固定到不可变 commit。

uiautomator2 来源：[Python core](https://github.com/openatx/uiautomator2/blob/657c5d791075945cc21e78e125b220461c8ae99c/uiautomator2/core.py#L76)、[Python click](https://github.com/openatx/uiautomator2/blob/657c5d791075945cc21e78e125b220461c8ae99c/uiautomator2/_selector.py#L138)、[当前 u2.jar dump](https://github.com/openatx/android-uiautomator-server-jar/blob/d0449b9da4b32ad28bee0d3c3f561c49010acf35/app/src/main/java/com/wetest/uia2/stub/AccessibilityNodeInfoDumper.java#L102)。当前 core 通过 app_process 启动 jar，不能用旧 atx-agent/APK 架构概括。底层 dump 通过跨屏窗口生成带 display-id 的树；Python UiObject.click 取坐标后交给全局 click，不能只给截图加 display_id 就称整条通路已隔离。未核对特定 wheel 所含 jar 与独立研究的 server commit 是否完全一致。

Mobile MCP 来源：[默认执行器](https://github.com/mobile-next/mobile-mcp/blob/63a5974d9bfa5b66d1ee4d1b0945df3ebea18b11/src/server.ts#L213)默认是 MobileDevice/mobilecli，旧 AndroidRobot 仅兼容开关；[mobilecli 中文路径](https://github.com/mobile-next/mobilecli/blob/7ca95dcaf443fb6fb5112da55009f1adf5d28856/devices/android.go#L948)设置剪贴板、粘贴、清空，[UiAutomation 初始化](https://github.com/mobile-next/mobilecli/blob/7ca95dcaf443fb6fb5112da55009f1adf5d28856/agents/android/java/UiAutomationFactory.java#L82)含显示参数的构造使用 0。MCP 锁文件解析 mobilecli 1.0.9，本次核对的是所链当前源码，未验证发布二进制与该 commit 完全一致。Mobile MCP 外壳 Apache-2.0，但 mobilecli 当前[许可证](https://github.com/mobile-next/mobilecli/blob/7ca95dcaf443fb6fb5112da55009f1adf5d28856/LICENSE)为 FSL 1.1/两年后另授 Apache，不能仅看外壳就复制整条依赖链。

Maestro 来源：[官方 MCP](https://github.com/mobile-dev-inc/maestro/blob/c436d39f2ba07c4241b7712f85aa5e889d90d62b/maestro-cli/src/main/java/maestro/cli/mcp/README.md)、[Android RPC](https://github.com/mobile-dev-inc/maestro/blob/c436d39f2ba07c4241b7712f85aa5e889d90d62b/maestro-proto/src/main/proto/maestro_android.proto#L35)、[Unicode 输入](https://github.com/mobile-dev-inc/maestro/blob/c436d39f2ba07c4241b7712f85aa5e889d90d62b/maestro-client/src/main/java/maestro/drivers/AndroidDriver.kt#L1365)。当前确实能填中文，但恢复旧输入法不能消除切换时已经发生的主屏干扰。

### 7.2 Appium 当前版本实际接通了什么

本次核验 UiAutomator2 driver **8.7.0**、server **10.6.6**、appium-android-driver **14.0.8** 的源码；[driver 依赖](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/package.json#L63)为 server `^10.6.0` 和 android-driver `^14.0.8`，这是兼容范围，不是已经安装验证的 lockfile。部署时还需锁定实际 Appium/Node/客户端/传递依赖。

后续机制实验的实际安装树为 Appium **3.7.0**、driver **8.7.0**、server **10.6.6**、android-driver **14.2.0**。重新核对了已安装代码中的 IME 初始化行为；不能把之前单独阅读的 14.0.8 写成实测版本，完整环境与产物哈希见实测报告。

server 的 [AndroidX 依赖](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/gradle/libs.versions.toml#L28)固定 UI Automator **2.3.0**；虽官方目前另有 2.4.0，Appium 反射多个内部接口，不擅自升级替换。

| 路径 | 源码证据 | 本项目使用方式 |
| --- | --- | --- |
| 副屏 XML | [AXWindowHelpers](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/utils/AXWindowHelpers.java#L106)：enableMultiWindows → getWindowsOnAllDisplays → get(currentDisplayId) → getRoot | 设备端先过滤后序列化；不把主屏树发送到电脑再删掉 |
| 元素定位 | [CustomUiDevice](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/internal/CustomUiDevice.java#L134)使用上述 roots；[BySelectorHelper](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/BySelectorHelper.java#L75)补 display 条件 | 开放核验过的 id/accessibility-id/class/XPath；resource-id 使用完整包名，不开放旧 UiSelector 表达式 |
| 中文直接填写 | [ElementHelpers](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/utils/ElementHelpers.java#L59)传 CharSequence 执行 ACTION_SET_TEXT；[replaceElementValue](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/lib/commands/element.ts#L169)传 replace:true | 不装 Unicode 键盘；校验节点归属与动作能力，重新读字段确认没有截断/误写 |
| 启动 | [mobileStartActivity](https://github.com/appium/appium-android-driver/blob/23da04d4111261c00f10c21ba19175ef6d41de03/lib/commands/intent.ts#L109)把 display 拼入 am start-activity --display | 适配层构造已审核启动参数；仍检查旧 task，不能靠参数保证后续页面不跳屏 |
| 触控/截图 | [元素手势](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/core/AxNodeInfoHelper.java#L173)取窗口 display；[截图](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/utils/ScreenshotHelper.java#L98)映射目标屏 | 现成能力存在；首版统一复用 scrcpy 帧与输入，避免再适配失败回退与截图 ID 映射 |

### 7.3 不能沿用的默认行为与有限补丁

1. **默认观察并不隔离。** 默认 enableMultiWindows=false 走 active root；[CurrentDisplayId](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/settings/CurrentDisplayId.java#L11)默认 0，-1 会 reset。可信适配器先绑定/回读，设备端 guard 检查非零目标显示及会话世代，成功前不开工具；失效不回落主屏。
2. **全局 Toast 另有采集通路。** [NewSession](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/handler/NewSession.java#L53)无条件开启监听；[NotificationListener](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/NotificationListener.java#L98)记录事件文本/日志，[Dumper](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/core/AccessibilityNodeInfoDumper.java#L230)再拼进 XML。事后 enableNotificationListener=false 不清缓存；小补丁从启动禁文本采集、清缓存并取消拼树，保证主屏内容留在设备。
3. **填写文本不能顺带发全局 Enter。** [SendKeysToElement](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/handler/SendKeysToElement.java#L63)检测字面反斜杠加 n 的尾缀后可能 pressEnter；这不是普通换行字符的等价描述。首版小补丁移除隐式 Enter，保留原文字串；需要 Enter 时另用 scrcpy 定向工具。
4. **手势的失败路径不同于正常能力。** AndroidX 2.3.0 GestureController 的 MotionEvent.setDisplayId 反射失败后仍继续，Appium [W3C 动作](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/utils/w3c/ActionsExecutor.java#L250)也有相同行为；节点 window=null 可回落0。[Back](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/utils/Device.java#L64)与普通 key 未绑定屏。首版只用 scrcpy 定向输入，不为所有 Appium 动作补实现。
5. **启动也会改全局状态。** [initDevice](https://github.com/appium/appium-android-driver/blob/23da04d4111261c00f10c21ba19175ef6d41de03/lib/commands/device/common.ts#L279)中 hideKeyboard=true 切 EmptyIME，false 也会 ime reset；应省略。设置 disableSuppressAccessibilityService=true 保留用户已启用的无障碍服务，skipLogcatCapture=true 避免默认全局日志；自动 App 启停、解锁/准备动作也需关闭或移到准备期，完整配置见[运行时契约](../superpowers/specs/2026-09-21-agent-runtime-contracts.md#5-phonesessionobservation-与动作工具)。

这些源码支持“复用后端并做有限适配”的判断，不等于原版 Appium 已满足完整隔离。全局 idle 等待、单会话限制和节点归属检查的进一步核验如下。

### 7.4 同时操作：会话不互斥，但默认等待策略不合适

本节仍区分源码机制和设备证据；AOSP 链接固定到与 2.3 相同的 Android 14 commit。

- **人的普通触摸不占用第二个 UiAutomation。** [UiAutomationManager](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/services/accessibility/java/com/android/server/accessibility/UiAutomationManager.java#L88)限制的是同时注册第二个自动化服务；[UiAutomation 回调](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/core/java/android/app/UiAutomation.java#L1786)没有“用户触摸就暂停 Appium”的逻辑。一个 Appium session 操作副屏，用户使用主屏在机制上可并行；不要为两块屏启动两个 UiAutomation，也不要在 Appium 活跃时运行 `uiautomator dump`。
- **`currentDisplayId` 不会让空闲检测只看副屏。** [UiAutomation](https://github.com/aosp-mirror/platform_frameworks_base/blob/6e47c7075b91983ae501114425ea25e6df7690c8/core/java/android/app/UiAutomation.java#L1791)按收到的所有无障碍事件更新同一个时间戳。AndroidX 2.3.0 的查询/节点刷新会等待全局静默，默认上限 10 秒；一次请求可能经过多次等待。主屏持续活动可以拖慢副屏，不是输入会话互斥。
- **候选配置固定 `waitForIdleTimeout=0`。** Appium 的 [WaitForIdleTimeout](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/settings/WaitForIdleTimeout.java)会更新 AndroidX Configurator。跳过全局 idle 启发式后仍有节点 refresh、动作结果等待和读回；不能宣称零延迟或不需状态确认。
- **显示守卫必须读当前窗口。** [UiObject2Element.getDisplayId](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/UiObject2Element.java#L172)取 AndroidX 创建元素时缓存的 display。设备端应刷新节点并读取 `node.getWindow().getDisplayId()`，窗口为空就拒绝；一次会话固定一个显示，重建废弃旧句柄。此处是代码审计发现的防护缺口，没有把潜在错路由描述为已观察到的故障。

后续实测：60.65 秒内，主屏完成 79 轮合成 composing/commit，副屏完成 141 轮中文替换、读回与定向点击；记录中主屏焦点和 IME 连接未变。默认 idle 的单次 source 为 10.1 秒，idle=0 的 141 次中位数为 120.72 毫秒。原版 server 的 Toast/特殊尾缀/设备端守卫仍未补齐，因此这些结果只支持机制可行，不能宣称原版工具满足所有隔离要求。方法及两个探针配置失败见[实测报告](../validation/2026-09-21-appium-concurrency-probe.md)。

### 7.5 结构化树可以代替每步截图输入

[Playwright MCP 官方 README](https://github.com/microsoft/playwright-mcp) 明确采用结构化 accessibility snapshots，并说明普通操作无需视觉模型；它并非只把整页 DOM 原样交给 LLM。原生 Android 虽没有统一 DOM，Appium 的 accessibility XML 也可转换为这类快照。决定采用“副屏树 → 压缩语义快照 → 文本 LLM；必要时副屏图 → VLM”，不会要求每轮 GUI 导航都走视觉模型。

Appium 的动作信息并非默认全部包含：[IncludeA11yActionsInPageSource](https://github.com/appium/appium-uiautomator2-server/blob/4a8139161cbb3aad078e36539995eb734297d56e/app/src/main/java/io/appium/uiautomator2/model/settings/IncludeA11yActionsInPageSource.java) 默认 false；须开启或由设备端直接读取实际 action list，才能向模型声明某字段允许 SET_TEXT。文本、属性和 bounds 的存在不证明该动作可用。

商业 App 的 WebView 不保证可读 DOM。[UiAutomator2 Hybrid Mode](https://github.com/appium/appium-uiautomator2-driver/blob/7a54db007aa8a44f5df21cd0b52afc13c0d277ae/README.md#hybrid-mode) 要求目标 WebView 正确配置且可调试；能读原生无障碍树不等于能接 Chrome DevTools。MVP 不切 WebView context，沿用副屏树与视觉补充；实际覆盖率待真实页面预检。

视觉只补观察缺口，不能修复不支持的中文填写、错误显示绑定或不可验证的操作结果。具体字段、ref 和失效处理见[运行时契约 5.1](../superpowers/specs/2026-09-21-agent-runtime-contracts.md#51-模型可读的语义快照)。

## 8. 本轮状态与视觉提取决策

持续会话状态沿用 LangGraph persistence 与既定存储分工，新增明确的[状态字段和权威归属](../superpowers/specs/2026-09-21-agent-runtime-contracts.md#21-持续维护的运行状态)。查询改写读取原话、历史与结构化任务状态；修改先进入持久控制事件再 replan，interrupt 恢复保留任务身份。Redis 聊天记录不代替 DAG、约束、授权和操作账本。

按用户选择，行程图片先交 VLM 直接识别，复用 LangChain 图像消息与结构化输出，不增加独立 OCR 服务。**这是 MVP 设计决定，不是当前配置模型已通过识别测试的结论。** 来源图片、原文/规范化字段、歧义随候选保存；确定性校验与真实日历核验分别检查“字段是否合理”和“是否真的写入”。具体流程见[主设计 11.1](../superpowers/specs/2026-09-21-wellphone-design.md#111-行程图片mvp-直接使用-vlm)，识别困难样本列入[验证计划](../validation/2026-09-21-feasibility-and-demo.md#a-行程截图--日历)。
