# V2 研究：通用编排、外置技能与真实 App 副屏操作

核验日期：2026-09-21。方法：实际获取官方网页、官方 Doc/源码和项目实现；不是只阅读项目简介。**没有启动模拟器、登录 App、调用模型/业务 API 或执行真实任务。** 下文“事实”来自资料，“决定”是本项目设计，“待测”不能写成已实现能力。

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

决定：底座固定版本后做小范围 server 修改，不继承主屏控制通道。scrcpy 提供传输和输入基础，规划、权限、skills、业务核验由本项目补齐。

### 1.2 AutoGLM 适合放在 GUI 执行决策层

事实：动作协议包括 `do(action="Tap", element=[x,y])`、Type、Swipe、Launch、Back、Wait、Take_over、finish；坐标约定为 0..999，现有执行器按 `/1000 * width` 换算。协议没有受信副屏身份，AST 解析也不能替代动作权限检查。

`Note` 和 `Call_API` 在核验执行器中是占位实现。原 Android 执行通道未完整指定 display，Type 会切换全局 ADB Keyboard。Tap 是否弹确认的一部分信息来自模型，不能单凭模型自报判断影响。详细通道审计保留在[首轮 R11–R12](2026-09-21-platform-research.md)。

来源：[提示词](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/config/prompts_zh.py)、[动作执行器](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/actions/handler.py)、[文字输入](https://github.com/zai-org/Open-AutoGLM/blob/86f55382982fb054e8fc98ca80609dff8a2cdc3c/phone_agent/adb/input.py)。本轮也重抓 main 关键文件复核上述行为。

决定：保留 PlannerModel / GuiModel 的接口分工，MVP 可用同一已配置模型承担两种角色；仅在能力/延迟测试证明需要时分开。不能假设 `LLM_MODEL` 支持图片、结构化规划或 GUI 定位，首日探测。GUI 模型生成的动作统一转换成受控工具 schema，不执行模型生成代码。

### 1.3 从汇总中追读的实际实现

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

### 2.3 ACTION_SET_TEXT 也需要完整焦点实验

事实：[TextView](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/core/java/android/widget/TextView.java#L14315) 的 SET_TEXT 使用 `setText` 和 `setSelection`，可传中文；但[服务端动作路径](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/services/accessibility/java/com/android/server/accessibility/AbstractAccessibilityServiceConnection.java#L2077) 在转发多种 node action 前会调用 `requestWindowFocus`。

进一步追到 [WindowState](https://github.com/aosp-mirror/platform_frameworks_base/blob/android14-release/services/core/java/com/android/server/wm/WindowState.java#L5973)：先移动 display，再处理 task focus。第一条路径检查能否抢 top focus，并不足以证明后续 task focus 路径完全不影响主屏。

决定：中文文本接口只能标为候选。必须在主屏连续拼音输入、选择候选词时，副屏反复执行 SET_TEXT、点击和返回，同时检查字符投递、IME target 和实际焦点。若失败，修底座或如实标受阻；不靠切输入法、全局剪贴板或业务 API 掩盖。

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
