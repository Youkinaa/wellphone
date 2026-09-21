# 通用 GUI Agent 运行时契约

日期：2026-09-21。状态：设计草案，未实现。与[主设计](2026-09-21-wellphone-design.md)配套，约定模块边界及恢复语义，不是逐业务固定 workflow。

## 1. 模块及最小接口

| 模块 | 接口职责 | 首版实现 |
| --- | --- | --- |
| RequestInterpreter | 原话、历史和活动任务 → 规范化请求/控制事件 | 规则 + 一次结构化模型调用 |
| SkillCatalog | 列元数据、选择并加载版本固定的技能内容 | 本地 Markdown；最多加载 3 个相关 skill |
| Planner | 请求、能力、skills、观察 → Plan / PlanPatch | 模型生成，确定性校验器把关 |
| Coordinator | 接收控制事件、调度、合并结果、修改计划 | LangGraph 固定状态图，单个 run owner |
| GuiExecutor | 节点目标 → 有界观察/行动循环 → 带证据结果 | LangChain 模型消息和结构化工具 |
| ToolRegistry / Gateway | 注册工具、校验参数、权限、状态与预算 | 可信代码；技能无权修改 |
| PhoneBackend | 副屏会话、观察、输入与目标 App 导航 | Appium UiAutomator2 + scrcpy + 受控适配层 |
| ConversationHistoryStore | `append_once/list_window/get_summary` | 普通 Redis，完整 LangChain message 编解码 |
| RunStore / OperationLedger | 计划版本、控制事件、执行意图与真实结果 | SQLite，独立于 checkpoint |
| CheckpointerFactory | 创建执行快照后端 | 文件型 AsyncSqliteSaver |
| ArtifactStore | 观察截图、树、证据与摘要的引用 | 本地目录，默认不进 Git |

建议代码目录为 `agent/{runtime,planning,messages,skills,tools,phone,storage}`、`patches/`、`skills/`、`app_profiles/`、`tests/`。本轮不创建实现骨架。`phone` 复用现有驱动并提供薄适配；`patches` 仅保存固定上游版本所需的有限修改，不默认新建完整 `android-bridge` 工程。没有日历或外卖业务数据接口。

## 2. 请求和标识

预留 `ActorContext(actor_id, workspace_id)`；MVP 由服务端固定为本地用户和默认工作区，不开放租户选择。后续增加租户字段应由可信身份层赋值，不让模型决定。

- `conversation_id`：一段用户对话，供 Redis 历史使用。
- `task_id`：一次可执行任务，同时作为 LangGraph `thread_id`。
- `request_revision`：用户对目标/约束的版本。
- `plan_revision`：经过校验的业务 DAG 版本。
- `node_id`：一个目标级工作项；`attempt_id` 标识其尝试。
- `operation_id`：一个真实副作用意图；重试不得随意换 ID。
- `session_id + session_epoch`：副屏生命周期；重建即失效。

RequestInterpreter 输出包含 `original_text`、`normalized_goal`、`intent`、`constraints`、`resolved_references`、`missing_slots`、`target_task_id`、`source_message_ids`。意图取值为 `ASK / NEW_TASK / MODIFY / CANCEL / APPROVE / STATUS / SUPPLY_INFO`；领域标签用于选 skill，不是业务 workflow 路由器。

MVP 一个 conversation 最多一个活动任务，一个设备最多一个执行会话。新的独立任务明确排队或替换，不隐式并行抢同一副屏。

### 2.1 持续维护的运行状态

Agent 是有状态运行时。下表描述逻辑字段及其权威归属，`RuntimeState` 是执行时组装的视图，不再独立维护一套事实副本。

| 状态 | 最小内容 | 权威来源 / 恢复规则 |
| --- | --- | --- |
| 对话与任务关联 | `conversation_id`、活动 `task_id`、输入消息引用、待回答问题 | 关联/待处理请求在 RunStore；完整 LangChain 消息在 Redis，投递可补齐 |
| 目标与约束 | 原话引用、规范化目标、实体/指代、预算/禁忌/时间、`request_revision` | RunStore；修改作为事件提交，历史摘要不得覆盖 |
| 计划与执行位置 | `plan_revision`、DAG、节点结果、当前节点/步骤与重试预算 | RunStore 保存计划和已接纳结果；checkpoint 保存可对账游标 |
| 中断与用户控制 | `accepted_control_seq`、`applied_control_seq`、暂停原因、待回复/授权关联 | RunStore 保存控制事实，checkpoint interrupt 与其对账 |
| 手机连接与观察 | serial、display、`session_epoch`、App/窗口元数据、最新 observation 引用 | 保存绑定意图及证据引用；恢复时重新连接/校验/观察，不反序列化旧元素句柄 |
| 现实操作与证据 | 授权引用、`operation_id`、提交/未知结果、artifact 引用 | OperationLedger 与 ArtifactStore；不知道结果时先核查，禁止盲重放 |

例如“预算改成 20 元”：先持久接纳修改并阻断新业务动作，再更新结构化预算与 request revision，生成 PlanPatch，保留未受影响的已完成事实；状态和对话中都能追溯到这条用户消息。已有待确认项若受修改影响，重新生成当前提案；旧确认不能误用于新参数。

进程恢复顺序固定为：加载任务关联和 RunStore → 对账 checkpoint/控制水位并盘点遗留操作，维持业务写入屏障 → 重连并校验副屏 → 获取新观察，开放必要的观察/核查导航以确认现实结果 → 未决副作用解除且当前控制事件/授权处理完毕后，由 coordinator 放行后续业务动作。连接前只能盘点账本，不能声称已核查 App；设备不可用或未知结果无法消除时保持可恢复暂停。

## 3. 业务 DAG schema

示例为计划片段，不表示只支持会议业务；`phone.*` 的具体动作在 agent_step 内根据页面选择。

```json
{
  "task_id": "task-017",
  "request_revision": 1,
  "plan_revision": 1,
  "goal": "创建明天下午三点的项目同步会议",
  "constraints": {"timezone": "Asia/Shanghai", "send_invites": false},
  "skill_refs": [{"id": "tencent-meeting", "version": "0.1", "content_hash": "resolved-by-catalog"}],
  "nodes": [
    {
      "id": "inspect_schedule",
      "kind": "agent_step",
      "goal": "查指定日期的会议并报告冲突",
      "depends_on": [],
      "inputs": {"date": {"from": "request", "path": "/resolved_date"}},
      "capabilities": ["phone.observe", "phone.launch_app", "phone.tap", "phone.swipe", "phone.back"],
      "resources": ["device:bound-session"],
      "completion_criteria": ["目标日期已核对", "可见会议的时间与主题已记录"],
      "budget": {"max_actions": 15, "max_local_retries": 2}
    },
    {
      "id": "create_meeting",
      "kind": "agent_step",
      "goal": "按已明确的主题和时间创建会议",
      "depends_on": ["inspect_schedule"],
      "inputs": {"schedule": {"from": "node", "node_id": "inspect_schedule", "path": "/result"}},
      "capabilities": ["phone.observe", "phone.tap", "phone.set_text", "phone.back"],
      "resources": ["device:bound-session"],
      "completion_criteria": ["从列表重新打开会议", "主题和起止时间一致", "会议号可见"],
      "budget": {"max_actions": 25, "max_local_retries": 2}
    }
  ]
}
```

计划前完成相对日期解析及缺失槽位确认；schema 示例省略了运行时填充的具体日期和完整参数。技能哈希由目录解析，不由模型自由写字符串。输入引用是受限 JSON 路径，不允许表达式执行、任意模板、文件路径或 Python 代码。

校验器必须检查：节点 ID 唯一、依赖存在且无环、引用只能访问允许的祖先输出/请求、required outputs 可用、工具存在且权限足够、会话绑定正确、预算有限、提交动作有授权核验路径、每个目标有可观察成功条件。

图的 `plan` 与实际 `node_runs` 分开。状态至少有 `PENDING / READY / RUNNING / WAITING / SUCCEEDED / FAILED / BLOCKED / CANCELLED / OUTCOME_UNKNOWN`。前驱的目标与证据验证通过后才允许后继 ready，不能把“工具没抛异常”当作任务成功。

## 4. 调度、并发和修改协议

LangGraph 只注册通用节点。`Command` 的动态路由不取消已配置静态边；每处只使用一种出边方案，避免双路执行。`Send` 预留给独立计算的 fan-out，首版不并发操作手机。

Coordinator 独占写 `plan/node_runs/task_status`。worker 返回带 `task_id, plan_revision, node_id, attempt_id, event_id` 的不可变事件。首版串行合并；未来并行事件使用按 ID 去重的 reducer，同 ID 不同内容报冲突，不能最后写入者无声覆盖。Send 和并行 reducer 不进入首版必需实现。

控制事件字段：`event_id, task_id, expected_plan_revision, control_seq, event_type, payload, source_message_id`。接入层持久化并通知 run owner，不与运行节点并发调用 `update_state`。任务保存 `accepted_control_seq` 和 `applied_control_seq`；存在未处理的修改/取消等控制事件时，网关禁止派发新业务动作。状态查询不增加此控制水位。

安全点位于每个设备原子动作之间。接收控制事件与派发动作共用本地仲裁锁，确定先后；派发前检查控制水位、计划版本和授权。模型调用中收到修改后，其旧结果即使 plan_revision 尚未变化也不可执行。已发出的 tap 必须先观察结果，不声称可撤回；外部输入与已发送动作间仍存在不可取消边界。暂停屏障允许读取必要状态以核对在途操作，不允许继续业务写入。

PlanPatch 包含基准版本、改动原因、增加/替换/取消节点、失效证据和可复用证据。RunStore 是权威来源，校验后在同一 SQLite 事务中 CAS 提交新 revision、控制事件消费水位及相关 outbox，再更新 checkpoint 的执行视图。已成功节点保留事实；修改其现实结果需要新节点，不改历史。失效传播到依赖变化的后继，复用观察重新核对新鲜度和前置条件。

通用 LangGraph 的 GUI 执行节点每次只推进一个原子动作，返回并保存游标/操作引用；业务 DAG 节点仍保持目标级。重启先从 RunStore 对账 checkpoint 的 revision 和控制水位，禁止旧快照直接发动作；遗留 `STARTED` 操作先核对或转 `OUTCOME_UNKNOWN`。业务提交不会因恢复而生成新 operation ID。图状态与手机操作仍无跨系统原子事务。

简单找不到按钮可局部再观察；超出局部重试预算、商家缺货、会议时间变化或用户修改目标才进入全局 replan。自动 replan 默认最多 2 次，用户明确修改单独计数；达到预算如实报告阻碍。

## 5. PhoneSession、Observation 与动作工具

PhoneSession 由可信执行器创建并注入：`device_serial, android_user, display_id, session_epoch, approved_packages, owner_task_id`。模型只引用 session，不允许指定任意 display。display ID 不是 ADB device serial。

PhoneBackend 独占 Appium session 和 scrcpy 控制通道，经本机 ADB 连接固定 serial。Appium 只绑定宿主 loopback，手机端服务限本地 ADB 转发通路；不开放外部 HTTP/广播，不开启任意 shell 等宽松功能。现有驱动的 session ID 不能冒充认证；网关隔离原始驱动入口，所需会话凭证/设备端绑定校验由有限补丁补齐并在 G1 验收，尚非上游默认能力。凭证不进入模型、公共日志或 skills。

模型只调用 `phone.*`，不能任意执行 Appium 命令、修改 settings、使用旧 `-android uiautomator` 选择器、切换 WebView context 或读全局日志。设备端保持绑定 display/epoch，拒绝非目标窗口节点、失效显示与未绑定请求；电脑端 guard 不能代替这一检查。

Observation 包含：`observation_id, session_epoch, display_id, package, activity, windows, frame_id, captured_at, viewport, rotation, screenshot_ref, tree_ref`。设备端在序列化前过滤非目标 display 的窗口、节点及事件内容；画面取自 scrcpy 绑定副屏。树与帧不是原子快照，窗口/旋转/画面不一致时重新观察。节点 ID 只在对应观察世代有效，不将 Appium 元素缓存当作跨页面或跨恢复的稳定句柄。

动作请求至少包含 `session_ref, observation_id, target, args, expected_package, expected_precondition`。执行前检查 epoch、App、窗口、旋转和目标新鲜度；页面变化则重新观察并重新定位。坐标以对应截图的尺寸/旋转解释，不能把旧图坐标直接打到新页面。

`phone.set_text` 只针对确认归属副屏、enabled/editable 且 action list 支持 SET_TEXT 的节点，以替换语义写入，再观察字段与焦点。Appium 默认 SendKeys 的追加/clear 路径和特殊尾缀触发全局 Enter 不可直接继承；该版本检测的是字面反斜杠加 n，不能混称普通换行。采用 `mobile:replaceElementValue` 的 `replace=true` 路径，并用有限补丁移除隐式 Enter，按键另走定向通道。尚不支持的文本返回 `UNSUPPORTED_TEXT_INPUT`，不静默改写文本或切换全局 IME/剪贴板。Enter、Back、tap/swipe 首版统一经 scrcpy 绑定显示注入，不启用 Appium 的全局 key/Back 或未核验 W3C actions。

`phone.launch_app` 只接 AppProfile ID，不接任意 Intent URI；执行器构造已测试的定向启动。启动前检查该包在主屏的全部现存 task/activity，包含后台旧任务；没有已验证的独立启动能力则拒绝，不自动迁移或 force-stop。用户在任务期间开始用同包时暂停，副屏销毁不搬回主屏或销毁用户原有 task。

scrcpy 整个运行会话固定 `clipboard_autosync=false`，控制消息白名单拒绝 GET/SET_CLIPBOARD；没有显式剪贴板工具也不意味着后台同步已关闭。`phone.back` 使用定向 `KEYCODE_BACK`，不使用可能在屏灭时触发 POWER 的 `TYPE_BACK_OR_SCREEN_ON`；模型无电源/系统设置操作入口。副屏显示失效或设备锁屏时暂停，不自动唤醒/解锁主屏。

这些 guard 降低错误概率，但不能为未经测试的 App 页面转移提供数学保证。任何主屏跳转都使该测试失败，不能用“立即停机”替代隔离验收。

Appium 启动配置属于可信部署配置，模型不可改写：

- 准备期安装/初始化 instrumentation；任务期固定 `autoLaunch=false`、`noReset=true`、`forceAppLaunch=false`、`shouldTerminateApp=false`、`skipUnlock=true`、`skipLogcatCapture=true`、`disableSuppressAccessibilityService=true`，不在用户使用时执行自动安装、清数据或改系统动画等准备动作。
- 省略 `hideKeyboard`，禁用 `unicodeKeyboard` 与全局剪贴板工具；`hideKeyboard=false` 仍会重置全局 IME。准备完成后才考虑 `skipDeviceInitialization` 等跳过选项，不能用它们掩盖未完成初始化。
- Gate 关闭时绑定非零 `currentDisplayId`，固定 `enableMultiWindows=true` 并回读核验；全局 Toast 文本采集从 server 启动即禁用，不依赖事后关监听的缓存过期。
- Appium 默认 display 为 0，`-1` 可重置设置；server 新会话/重连必须先重新绑定，设备端绑定校验未通过就拒绝观察和动作。旧元素引用随会话世代失效。
- 默认 Appium gesture 注入存在定向设置失败后继续执行的路径；首版复用 scrcpy 的失败即拒绝通道。以后启用 Appium gesture 必须先修该路径和节点窗口为空回落 display 0 的行为，再单独验收。

上述约束与上游固定版本关系见[研究第 7 节](../../research/2026-09-21-agent-runtime-and-gui-research.md#7-复用手机自动化框架与-mcp)，不能用安装最新版代替依赖锁定和运行验收。

## 6. skills 与 AppProfile 的数据边界

技能文档示意：

```yaml
---
id: tencent-meeting
version: "0.1"
description: 查询、预约和核对腾讯会议中的未来常规会议
required_capabilities:
  - phone.observe
  - phone.launch_app
  - phone.tap
  - phone.set_text
app_profiles:
  - tencent-meeting-tested
---
```

正文应包含适用意图、需要明确的主题/日期/时区/时长、可借鉴的页面语义、如何识别成功、何时停止和常见误操作。例如提示“从会议列表重新打开核验”“避免误入会”“关闭非请求的添加日历选项”。它不提供固定像素轨迹或绕过权限的命令。

工具权限、风险级别与全局策略由可信 Registry/Gateway 决定。`required_capabilities` 只是声明需求，缺少能力时 skill 不可执行。UI 文字、截图、网页和技能检索返回的资料不能动态新增工具或关闭 guard。

AppProfile 保存已验证包名/版本、启动行为、可用控件语义、提交入口分类和结果辨识规则；应支持语义匹配和版本范围，不把永久固定坐标作为唯一依据。未知页面或控件影响默认保守处理。新增 skill 只改变知识；新增原子能力需要代码、测试与能力注册。

首版检索采用元数据过滤、关键词和模型选择，不引入向量数据库。允许多个 skill 组合到同一 DAG，例如“建会议后把时间放到日历”，但跨 App 的每个动作仍走同一副屏锁和各自验证。

## 7. 授权、操作账本与恢复

策略区分观察、导航、编辑草稿、持久创建/修改、外发/订单提交、支付。级别来自工具和 AppProfile 当前上下文，而非仅靠模型填写的风险标签。已有用户指令足够明确并覆盖参数时可直接执行；缺少信息或授权才暂停。

ActionProposal 至少记录 `operation_id, target, canonical_args_hash, amount/address/items/time_scope, task_id, granted_plan_revision, policy_version, evidence_refs`。授权绑定动作摘要、允许范围和有效期，版本记录其来源。无关 replan、复核价格但金额未变时可重新验证并复用；换地址、换商品或金额/其他条件超出原授权范围时失效，记录覆盖关系的验证结果。

提交前账本记录 `PREPARED → STARTED`；观察确认后为 `CONFIRMED`，明确未执行为 `FAILED`，提交后超时为 `OUTCOME_UNKNOWN`。同一操作重启或重试复用 operation ID；GUI 没有可靠服务端幂等键，本地 ID 不能消除重复下单风险。

核验流程是实际重新打开 App 的列表/详情：日历比较时间、标题和位置；会议比较主题、时间及可见会议号；订单比较商家、商品、总价、地址摘要、创建时段与可见订单标识。日历 UI 不显示 event ID 时，保存可见字段与截图，不伪造系统 event ID。

结果未知时，找到唯一充分匹配才能确认。无匹配、多匹配、读取受限或用户同时修改都不能作为自动再点提交的理由。保留待人工核查状态。取消尚未执行的节点立即生效；取消已经发生的业务是新任务，不自动删除会议、清空用户原有购物车或退款。

interrupt 在独立审阅节点，节点前只做可重放的准备工作。恢复使用相同 thread 与 `Command(resume=...)`；新任务输入用正常 state 输入，不把 resume 当万能更新方式。MVP 只允许安全继续执行，不提供会重放真实提交动作的任意 time-travel 按钮。

## 8. 消息、Redis 与 checkpoint

LangChain 消息保留类型、ID、内容块、`AIMessage.tool_calls` 和 `ToolMessage.tool_call_id`。工具调用组完整进入或离开上下文；大截图和树放 artifact，Redis 存引用；本次视觉调用由适配器加载必要截图为实际图像内容块，不重复附带全部历史图像。`add_messages` 按 ID 合并，不是内容去重器。

上下文由系统约束、选中 skills、规范化请求、结构化任务状态、必要摘要、最近完整消息组和当前观察构成。先预算 token，再压缩历史；不能压缩掉仍有效的预算、禁忌、授权和未完成 tool call。

Redis 使用列表/哈希/集合等基本命令封装 `append_once(message_id)`；写入顺序和去重操作应原子执行。历史保留策略先不自动过期，使用持久 volume 和明确的 Redis 持久化配置；清理接口保留，截图另行设本地保留期限。

SQLite RunStore 持久保存已接收请求、权威计划版本、操作账本及待投递对话事件。Redis 是会话历史查询层，投递按稳定 message ID 去重；暂时不可用时重试补齐，不伪造已同步。checkpoint 保存可对账的执行游标，账本是副作用恢复依据；每次恢复都先核对 RunStore，不能用旧 checkpoint 覆盖已接纳的新计划。即使用同一 SQLite 文件，也不假设框架 checkpoint、账本和 Android 点击构成原子事务。

单进程按 task/device 加锁，graph state 单一写者。未来替换 RedisSaver/Postgres 或增加多个 worker 时，要新增分布式所有权、租约与 fencing，本版不提前实现。
