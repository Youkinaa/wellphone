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
| PhoneBackend | 副屏会话、观察、输入与目标 App 导航 | scrcpy + 小型 Accessibility 桥 |
| ConversationHistoryStore | `append_once/list_window/get_summary` | 普通 Redis，完整 LangChain message 编解码 |
| RunStore / OperationLedger | 计划版本、控制事件、执行意图与真实结果 | SQLite，独立于 checkpoint |
| CheckpointerFactory | 创建执行快照后端 | 文件型 AsyncSqliteSaver |
| ArtifactStore | 观察截图、树、证据与摘要的引用 | 本地目录，默认不进 Git |

建议代码目录为 `agent/{runtime,planning,messages,skills,tools,phone,storage}`、`android-bridge/`、`skills/`、`app_profiles/`、`tests/`。本轮不创建实现骨架。`android-bridge` 只处理观察与 GUI 操作，不提供日历或外卖数据代办接口。

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

桥接命令经本机 ADB 通路，以每会话凭证鉴别 SessionBroker 并绑定上述身份；具体传输在底座探针中确定。不得开放无鉴权广播/HTTP 控制入口；会话凭证不进入模型、公共日志或 skills。桥本地执行显示范围与工具白名单校验，不能只依赖电脑端检查。

Observation 包含：`observation_id, session_epoch, display_id, package, activity, windows, frame_id, captured_at, viewport, rotation, screenshot_ref, tree_ref`。桥在本地过滤所有非目标 display 的窗口、节点、事件和截图。节点 ID 只在对应观察世代有效，不缓存跨页面的 AccessibilityNodeInfo 对象。

动作请求至少包含 `session_ref, observation_id, target, args, expected_package, expected_precondition`。执行前检查 epoch、App、窗口、旋转和目标新鲜度；页面变化则重新观察并重新定位。坐标以对应截图的尺寸/旋转解释，不能把旧图坐标直接打到新页面。

`phone.set_text` 只针对确认归属副屏、enabled/editable 且 action list 支持 SET_TEXT 的节点，执行后重新观察字段与焦点。若不支持安全中文填入，返回 `UNSUPPORTED_TEXT_INPUT`，不切换全局 IME、剪贴板或操作主屏键盘。Enter、Back 等也绑定显示设备并接受影响判定。

`phone.launch_app` 只接 AppProfile ID，不接任意 Intent URI；执行器构造已测试的定向启动。启动前检查该包在主屏的全部现存 task/activity，包含后台旧任务；没有已验证的独立启动能力则拒绝，不自动迁移或 force-stop。用户在任务期间开始用同包时暂停，副屏销毁不搬回主屏或销毁用户原有 task。

这些 guard 降低错误概率，但不能为未经测试的 App 页面转移提供数学保证。任何主屏跳转都使该测试失败，不能用“立即停机”替代隔离验收。

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

LangChain 消息保留类型、ID、内容块、`AIMessage.tool_calls` 和 `ToolMessage.tool_call_id`。工具调用组完整进入或离开上下文；大截图和树放 artifact，不把它们反复塞进 Redis 和 prompt。`add_messages` 按 ID 合并，不是内容去重器。

上下文由系统约束、选中 skills、规范化请求、结构化任务状态、必要摘要、最近完整消息组和当前观察构成。先预算 token，再压缩历史；不能压缩掉仍有效的预算、禁忌、授权和未完成 tool call。

Redis 使用列表/哈希/集合等基本命令封装 `append_once(message_id)`；写入顺序和去重操作应原子执行。历史保留策略先不自动过期，使用持久 volume 和明确的 Redis 持久化配置；清理接口保留，截图另行设本地保留期限。

SQLite RunStore 持久保存已接收请求、权威计划版本、操作账本及待投递对话事件。Redis 是会话历史查询层，投递按稳定 message ID 去重；暂时不可用时重试补齐，不伪造已同步。checkpoint 保存可对账的执行游标，账本是副作用恢复依据；每次恢复都先核对 RunStore，不能用旧 checkpoint 覆盖已接纳的新计划。即使用同一 SQLite 文件，也不假设框架 checkpoint、账本和 Android 点击构成原子事务。

单进程按 task/device 加锁，graph state 单一写者。未来替换 RedisSaver/Postgres 或增加多个 worker 时，要新增分布式所有权、租约与 fencing，本版不提前实现。
