# 通用 GUI Agent 运行时契约

日期：2026-09-21。状态：MVP 设计依据，未实现。与[主设计](2026-09-21-wellphone-design.md)配套，约定模块边界、交换数据及持久化协议；任务状态、完整时序和用户交接以[执行流程](2026-09-21-execution-flows.md)为准，不是逐业务固定 workflow。

## 1. 模块及最小接口

以下是同一后端进程内的职责，不是独立服务。表中调用均由可信代码组织；模型只提出数据或工具调用建议，不能自行串起另一套执行循环。

| 模块 | 触发方 / 时机 | 输入 | 输出 → 消费者 | 职责与首版边界 |
| --- | --- | --- | --- | --- |
| Interaction API | Web 上传、发送、控制、查询或 SSE 连接 | 图片字节；消息/控制/确认 DTO；查询游标 | `InputArtifact`、`Receipt`、`TaskView`、事件 → Web；已持久请求 → Coordinator | FastAPI 同源入口，校验并接纳请求；不规划、不直接操作设备；HTTP 细节见交互应用设计 |
| RequestInterpreter | Coordinator 取到新消息或用户补充 | 原话、输入图引用、必要历史、当前任务与待回复项 | `NormalizedRequest`、字段候选、缺失槽位 → Coordinator | 规则优先，必要时调用同一 ModelAdapter；解释目标、指代与修改；按需用 VLM 提取上传原图，不操作手机 |
| SkillCatalog | Coordinator 在目标明确后选择技能，或 replan 改变所需能力 | 规范化目标、领域线索、可用工具、已测 AppProfile | 固定版本的 `SkillBundle` → Planner、GuiExecutor | 先按元数据/关键词筛选，必要时经 ModelAdapter 比较候选；读取本地 Markdown，最多加载 3 个 skill；只提供知识，不取得执行权 |
| Planner | Coordinator 首次建图或决定 replan | 当前请求/约束、SkillBundle、可用工具、已有 Plan/节点结果及必要观察 | 候选 `Plan` / `PlanPatch`，或待澄清内容 → Coordinator | 调用模型形成目标级 DAG；Coordinator 使用确定性校验器接纳，Planner 不写权威版本 |
| Coordinator | 应用启动恢复、已接纳消息/控制、步骤返回、用户回复 | RunStore 权威状态、Interpreter/Planner/GuiExecutor 返回、控制事件 | 调用后续模块；持久任务/计划/节点结果；`PendingInteraction`、进度和终态事件 → API/outbox | 唯一 run owner，负责状态与顺序；LangGraph 固定通用图；澄清、授权和接管复用现有 interrupt，不新增交接服务 |
| GuiExecutor | Coordinator 调用一个 ready 节点的 `step` | `StepContext`：节点目标、已解析输入、技能、游标、允许工具及当前会话 | `StepResult` → Coordinator；工具建议 → Gateway | 每次观察/判断后至多派发一个改变设备状态的原子动作，再让出控制；动作成功不等于节点目标完成 |
| ModelAdapter（LangChain） | Interpreter 理解/提取、SkillCatalog 比较候选、Planner 建图、GuiExecutor 决策时按需调用 | `ModelRequest`：消息、图片引用、输出 schema、允许工具 schema | `ModelReply`：结构化候选或工具建议 → 原调用方 | 统一模型接口与消息编解码，按引用加载实际图像载荷；不执行工具，不另建模型服务 |
| ToolRegistry / Gateway | Coordinator/GuiExecutor 获取能力或请求工具；恢复时请求必要核查 | 工具名/参数、任务版本与控制水位、Observation、授权与操作引用 | `ToolSpec` 或 `ActionResult` → 调用方；授权提案随步骤返回 Coordinator | Registry 声明现有工具；Gateway 在一个入口检查范围/版本/授权，记录提交意图后调用后端；不建通用策略 DSL |
| PhoneBackend | Gateway 执行 `phone.*` | 已校验的会话、观察/动作请求 | `PhoneSession`、`Observation`、设备执行结果 → Gateway | 独占 Appium/scrcpy 通道；负责副屏连接、观察和定向操作；不决定业务目标或授权 |
| ConversationHistoryStore | Coordinator 准备上下文；outbox 投递或 API 查询历史 | conversation/message ID、消息记录、窗口范围 | LangChain 消息窗口/摘要、投递结果 → Coordinator/API | 普通 Redis 的 `append_once/list_window/get_summary`；保存对话历史，不覆盖 RunStore 的执行事实 |
| RunStore / OperationLedger | API 接纳；Coordinator 变更任务；Gateway 记录真实操作；启动时对账 | 请求/控制、版本化计划/结果、操作意图/证据、outbox 事件 | receipt、权威状态、控制水位、操作状态、待投递事件 → 原调用方 | SQLite；按既有事务协议读写。API 写接纳事实，Coordinator 独占计划/节点/任务状态，Gateway 写操作账本；不把 checkpoint 当提交凭据 |
| CheckpointerFactory / checkpoint | 应用初始化创建；LangGraph 在步骤边界保存、恢复 | 本地配置；thread ID、执行游标/操作引用 | AsyncSqliteSaver 及执行快照 → LangGraph/Coordinator | 复用文件型 AsyncSqliteSaver；恢复先与 RunStore 对账，不启动第二个调度器 |
| ArtifactStore | API 上传；PhoneBackend 保存观察；模型调用加载图片；执行器登记证据 | 图片/树/结果字节、来源元数据或本任务 artifact 引用 | 不可变文件引用/摘要，或实际载荷 → API、ModelAdapter、执行器 | 本地目录；输入原图与设备观察来源分开；有消费者的材料保留，默认不进 Git |

### 1.1 最小交换数据

以下描述数据形状，不是新增框架或逐模块消息总线；可以用普通类型化对象实现。标有 `?` 的字段允许缺省；ID、版本、会话和控制水位由可信代码生成/注入，模型输出不能覆盖。大图片、原始树和完整轨迹用 artifact 引用，具体载荷只在需要时读取。

| 数据 | 最小内容 / 返回种类 | 生产者 → 消费者 |
| --- | --- | --- |
| `RequestEnvelope` | `conversation_id, client_message_id, text, artifact_ids[], target_task_id?`；对待回复项的响应另绑定其 `pause_id` | API 接纳到 RunStore → Coordinator/Interpreter |
| `Receipt` | `receipt_id, source_id, task_id?, accepted_at, control_seq?`；同请求重发返回同一 receipt，接纳不表示执行成功 | RunStore/API → Web；任务尚未创建时 `task_id` 可为空，后续事件补关联 |
| `NormalizedRequest` | 第 2 节的目标、约束、意图、指代、缺失槽位、输入图与消息来源；图中提取字段保留原值/规范化值和来源 | Interpreter → Coordinator 校验并持久化 → Planner |
| `SkillBundle` | `skills[{id,version,content_hash,content,required_capabilities}], app_profile_refs[]` | SkillCatalog → Planner/GuiExecutor |
| `ModelRequest / ModelReply` | 请求为 `messages, image_refs[], output_schema?, tool_schemas[]`；返回为 `message, parsed_output?, tool_calls[]`。文本解释、图像字段、技能选择、计划、工具建议是不同的调用用途 | Interpreter/SkillCatalog/Planner/GuiExecutor ↔ ModelAdapter；调用方校验返回，不在适配器执行动作 |
| `Plan / PlanPatch` | 第 3–4 节的目标级 DAG、版本、节点输入/能力/完成条件，或基于旧版本的变更 | Planner → Coordinator 校验/提交 → GuiExecutor |
| `StepContext` | `task_id, plan_revision, node_id, attempt_id, goal, resolved_inputs, cursor, skill_refs, allowed_tools, budget, session_ref?, latest_observation_ref?`；需要手机动作时必须有有效会话，所带观察仍须核验新鲜度 | Coordinator → GuiExecutor |
| `ToolSpec` | `name,input_schema,output_kind,effect,required_capabilities`；当前节点允许工具是 Registry 与已接纳计划能力的交集 | Registry → Coordinator/GuiExecutor/ModelAdapter；只暴露声明，不授予额外能力 |
| `ToolCall / ActionResult` | 调用含 `tool_name,args` 与可信任务上下文，手机字段见第 5 节；返回含 `status,payload,evidence_refs,operation_id?`，状态为 `OK / REJECTED / NEEDS_AUTHORIZATION / FAILED / OUTCOME_UNKNOWN` | GuiExecutor/Gateway ↔ 后端；结果回到当前 step。`NEEDS_AUTHORIZATION` 携带具体 ActionProposal，不当作普通失败重试 |
| `NodeResult` | `outputs, completion_checks, evidence_refs`；checks 对应节点完成条件，结论区分已观察事实与未完成部分 | GuiExecutor → Coordinator 核验后写 `node_runs`，并向后继解析输入 |
| `StepResult` | `task_id,plan_revision,node_id,attempt_id,event_id,kind,cursor,payload,evidence_refs`；`kind` 为 `CONTINUE / NODE_RESULT / PAUSE / FAILED`，分别承载动作进度、NodeResult、暂停原因/待交互内容或尝试失败 | GuiExecutor → Coordinator；这些是步骤返回种类，不是任务状态或操作账本状态 |
| `PendingInteraction` | `pause_id,task_id,status,reason,prompt,expected_response,plan_revision,accepted_control_seq,source_refs,proposal_id?`；`status=OPEN / RESOLVED / SUPERSEDED`；`expected_response` 描述所需字段/候选，或 `decision/done` 类型。授权精确参数通过 proposal 引用读取，不再复制 | Coordinator 持久化 → API/Web；只展示当前 OPEN 待办，旧记录用于追溯；状态流转见执行流程 |
| `UserResponse` | `event_id,pause_id,response,expected_plan_revision,expected_control_seq,proposal_id?,operation_id?,canonical_args_hash?`；自然语言回复由消息接纳路径关联同一稳定 ID；授权回复须带后三项 | API 持久接纳 → Coordinator 核对当前待办；旧待办回复不套到新待办，同 ID 回复不重复应用 |
| `TaskView / TaskEvent` | 快照含 `task_id,status,plan_revision,accepted_control_seq,applied_control_seq,progress,pending_interaction?,result?`；事件含 `event_seq,task_id,plan_revision,type,payload`，暂停/控制事件的 payload 保留当前暂停标识与控制水位 | RunStore 已提交事实 → API/Web；SSE 与快照水位规则见交互应用设计 |

`InputArtifact`、`PhoneSession`、`Observation` 的字段归第 5 节；控制事件归第 4 节，授权提案和操作账本归第 7 节。任务级 `TaskStatus` / `PauseReason` 及其转换只在执行流程中定义；本文件的节点、步骤返回与操作状态各自表达不同层次，不能互相赋值。

输入图提取由 Interpreter 按需调用 ModelAdapter，输出候选业务字段；Coordinator 先做确定性日期/时区等校验，再交给 Planner。后续缺失信息走同一用户补充路径，不新建一个图片业务执行器。GUI 视觉定位由 GuiExecutor 发起，只使用当前副屏 Observation；两条路径共用模型适配器，上传图不能产生设备点击坐标。

Interpreter 的缺失槽位、Planner/GuiExecutor 无法消除的歧义、Gateway 的授权不足都返回 Coordinator。只有 Coordinator 建立/解除持久暂停并触发现有 interrupt；自然语言分类为 `APPROVE` 只是意图候选，必须关联当前具体提案、校验参数和已有授权，不能直接放行提交。工具或模型模块不得自行等待用户并私自恢复动作。

### 1.2 MVP 实现边界

- 先完成“接纳输入 → 理解与必要澄清 → 选技能/计划 → 观察与单步工具 → 核验结果 → 回显”正常主线，再覆盖已有依据的失败。单后端进程、一个 Coordinator、一个活动任务，复用同一工具和 skills；上传/API/模型适配均不另部署服务。
- 必须保留的约束是副屏范围和观察新鲜度、控制请求阻断旧动作、具体业务授权、请求去重，以及已提交但结果未知时禁止盲重放。缺条件时用现有暂停/用户交接解决，不为每个模块复制检查链。
- 首版恢复只做持久请求/当前计划/控制水位与操作账本对账、重连后重新观察；无法判断既有副作用时保持暂停并交用户核查。复杂自动补偿、跨任意历史节点恢复、分布式租约/多 worker、通用策略 DSL 和全场景异常矩阵推迟；不因此删除已有未知结果屏障。
- 不为未实现能力建立影子执行器、并行存储真相或仅供演示的业务结果。模块接口用当前消费者需要的字段即可；测试替身只用于明确标注的测试，不能冒充真实 App 验收。

建议代码目录为 `agent/{runtime,planning,messages,skills,tools,phone,storage}`、`patches/`、`skills/`、`app_profiles/`、`tests/`；新增交互层建议使用 `web/` 与 `agent/api/`。这些是拟定目录，当前尚无产品实现骨架。`phone` 复用现有驱动并提供薄适配；`patches` 仅保存固定上游版本所需的有限修改，不默认新建完整 `android-bridge` 工程。没有日历或外卖业务数据接口。新增 HTTP/SSE 接入语义以[交互应用设计](2026-09-21-interaction-app-design.md)为准。

## 2. 请求和标识

预留 `ActorContext(actor_id, workspace_id)`；MVP 由服务端固定为本地用户和默认工作区，不开放租户选择。后续增加租户字段应由可信身份层赋值，不让模型决定。

- `conversation_id`：一段用户对话，供 Redis 历史使用。
- `task_id`：一次可执行任务，同时作为 LangGraph `thread_id`。
- `request_revision`：用户对目标/约束的版本。
- `plan_revision`：经过校验的业务 DAG 版本。
- `node_id`：一个目标级工作项；`attempt_id` 标识其尝试。
- `operation_id`：一个真实副作用意图；恢复、重复请求及核查不换 ID，未知结果不能靠新 ID 绕过。
- `session_id + session_epoch`：副屏生命周期；重建即失效。

RequestInterpreter 输出包含 `original_text`、`normalized_goal`、`intent`、`constraints`、`resolved_references`、`missing_slots`、`target_task_id`、`source_message_ids`、`input_artifact_ids`、`field_candidates`。无图片时后两项可为空；字段候选保留 `field_name,raw_value,normalized_value,source_artifact_id,source_excerpt,ambiguities`，尚未确定的关键字段不能编造。意图取值为 `ASK / NEW_TASK / MODIFY / PAUSE / RESUME / CANCEL / APPROVE / STATUS / SUPPLY_INFO`；暂停/继续按钮直接走控制接纳，不等待模型分类。领域标签用于选 skill，不是业务 workflow 路由器。

MVP 全局最多一个活动任务，一个设备最多一个执行会话。已有活动任务时，新独立请求返回忙碌/澄清；只有用户明确结束或取消旧任务后才接纳替换，不实现任务队列，也不隐式并行抢同一副屏。旧任务的未决副作用仍按第 7 节保留核查屏障。

### 2.1 持续维护的运行状态

Agent 是有状态运行时。下表描述逻辑字段及其权威归属，`RuntimeState` 是执行时组装的视图，不再独立维护一套事实副本。

| 状态 | 最小内容 | 权威来源 / 恢复规则 |
| --- | --- | --- |
| 对话与任务关联 | `conversation_id`、活动 `task_id`、输入消息/附件引用、待回答问题、客户端 receipt | 关联/待处理请求在 RunStore；完整 LangChain 消息在 Redis，投递可补齐；客户端只缓存展示状态 |
| 目标与约束 | 原话引用、规范化目标、实体/指代、预算/禁忌/时间、`request_revision` | RunStore；修改作为事件提交，历史摘要不得覆盖 |
| 计划与执行位置 | `plan_revision`、DAG、节点结果、当前节点/步骤与重试预算 | RunStore 保存计划和已接纳结果；checkpoint 保存可对账游标 |
| 中断与用户控制 | `accepted_control_seq`、`applied_control_seq`、`pause_id`、暂停原因、待回复/授权关联 | RunStore 保存控制事实，checkpoint interrupt 与其对账 |
| 手机连接与观察 | serial、display、`session_epoch`、App/窗口元数据、最新 observation 引用 | 保存绑定意图及证据引用；恢复时重新连接/校验/观察，不反序列化旧元素句柄 |
| 现实操作与证据 | 授权引用、`operation_id`、提交/未知结果、artifact 引用 | OperationLedger 与 ArtifactStore；不知道结果时先核查，禁止盲重放 |

例如“预算改成 20 元”：先持久接纳修改并阻断新业务动作，再更新结构化预算与 request revision，生成 PlanPatch，保留未受影响的已完成事实；状态和对话中都能追溯到这条用户消息。已有待确认项若受修改影响，重新生成当前提案；旧确认不能误用于新参数。

进程恢复顺序固定为：加载任务关联和 RunStore → 对账 checkpoint/控制水位并盘点遗留操作，维持业务写入屏障 → 重连并校验副屏 → 获取新观察，开放必要的观察/核查导航以确认现实结果 → 未决副作用解除且当前控制事件/授权处理完毕后，由 coordinator 放行后续业务动作。连接前只能盘点账本，不能声称已核查 App；设备不可用或未知结果无法消除时保持可恢复暂停。

## 3. 业务 DAG schema

`TaskPlan` 是完整任务计划的类型名，下文简写为 `Plan`；`PlanPatch` 是对它的版本化变更，不是另一张 LangGraph 图。

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
      "inputs": {"date": {"from": "request", "path": "/constraints/resolved_date"}},
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
      "inputs": {"schedule": {"from": "node", "node_id": "inspect_schedule", "path": "/outputs/schedule"}},
      "capabilities": ["phone.observe", "phone.tap", "phone.set_text", "phone.back"],
      "resources": ["device:bound-session"],
      "completion_criteria": ["从列表重新打开会议", "主题和起止时间一致", "会议号可见"],
      "budget": {"max_actions": 25, "max_local_retries": 2}
    }
  ]
}
```

计划前完成相对日期解析及缺失槽位确认；schema 示例省略了运行时填充的具体日期和完整参数。技能哈希由目录解析，不由模型自由写字符串。输入引用是受限 JSON 路径，不允许表达式执行、任意模板、文件路径或 Python 代码。

`from=request` 的路径根为已接纳的 NormalizedRequest；`from=node` 的根为已核验的前驱 NodeResult。本例日期保存于 `constraints.resolved_date`，查询节点输出 `outputs.schedule`，字段尚不可用时不得把引用当值传给后继。

校验器必须检查：节点 ID 唯一、依赖存在且无环、引用只能访问允许的祖先输出/请求、required outputs 可用、工具存在且权限足够、会话绑定正确、预算有限、提交动作有授权核验路径、每个目标有可观察成功条件。

图的 `plan` 与实际 `node_runs` 分开。节点状态 `NodeStatus` 至少有 `PENDING / READY / RUNNING / WAITING / SUCCEEDED / FAILED / BLOCKED / CANCELLED / OUTCOME_UNKNOWN`，不充当任务级 TaskStatus。前驱的目标与证据验证通过后才允许后继 ready，不能把“工具没抛异常”当作任务成功。

## 4. 调度、并发和修改协议

LangGraph 只注册通用节点。`Command` 的动态路由不取消已配置静态边；每处只使用一种出边方案，避免双路执行。`Send` 预留给独立计算的 fan-out，首版不并发操作手机。

Coordinator 独占写 `plan/node_runs/task_status`。worker 返回带 `task_id, plan_revision, node_id, attempt_id, event_id` 的不可变事件。首版串行合并；未来并行事件使用按 ID 去重的 reducer，同 ID 不同内容报冲突，不能最后写入者无声覆盖。Send 和并行 reducer 不进入首版必需实现。

控制事件字段：`event_id, task_id, expected_plan_revision, control_seq, event_type, payload, source_message_id`。接入层持久化并通知 run owner，不与运行节点并发调用 `update_state`。任务保存 `accepted_control_seq` 和 `applied_control_seq`；存在未处理的修改/取消等控制事件时，网关禁止派发新业务动作。状态查询不增加此控制水位。

暂停可能不改变计划版本，故 `RESUME` 还须绑定 `expected_control_seq` 和当前 `pause_id`，在同一仲裁锁内校验，不能由延迟到达的继续请求解除后来的暂停。`PAUSE/CANCEL` 对同一未终结任务的停止意图即使基准 plan revision 已旧仍接纳，返回当前水位与实际应用状态；不得跨 task 作用。终态任务返回实际终态，未决副作用的核查屏障继续保留。

安全点位于每个设备原子动作之间。接收控制事件与派发动作共用本地仲裁锁，确定先后；派发前检查控制水位、计划版本和授权。模型调用中收到修改后，其旧结果即使 plan_revision 尚未变化也不可执行。已发出的 tap 必须先观察结果，不声称可撤回；外部输入与已发送动作间仍存在不可取消边界。暂停屏障允许读取必要状态以核对在途操作，不允许继续业务写入。

PlanPatch 包含基准版本、改动原因、增加/替换/取消节点、失效证据和可复用证据。RunStore 是权威来源，校验后在同一 SQLite 事务中 CAS 提交新 revision、控制事件消费水位及相关 outbox，再更新 checkpoint 的执行视图。已成功节点保留事实；修改其现实结果需要新节点，不改历史。失效传播到依赖变化的后继，复用观察重新核对新鲜度和前置条件。

通用 LangGraph 的 GUI 执行节点每次只推进一个原子动作，返回并保存游标/操作引用；业务 DAG 节点仍保持目标级。重启先从 RunStore 对账 checkpoint 的 revision 和控制水位，禁止旧快照直接发动作；遗留 `STARTED` 操作先核对或转 `OUTCOME_UNKNOWN`。业务提交不会因恢复而生成新 operation ID。图状态与手机操作仍无跨系统原子事务。

简单找不到按钮可局部再观察；超出局部重试预算、商家缺货、会议时间变化或用户修改目标才进入全局 replan。自动 replan 默认最多 2 次，用户明确修改单独计数；达到预算如实报告阻碍。

## 5. PhoneSession、Observation 与动作工具

PhoneSession 由可信执行器创建并注入：`device_serial, android_user, display_id, session_epoch, approved_packages, owner_task_id`。模型只引用 session，不允许指定任意 display。display ID 不是 ADB device serial。

PhoneBackend 独占 Appium session 和 scrcpy 控制通道，经本机 ADB 连接固定 serial。Appium 只绑定宿主 loopback，手机端服务限本地 ADB 转发通路；不开放外部 HTTP/广播，不开启任意 shell 等宽松功能。现有驱动的 session ID 不能冒充认证；网关隔离原始驱动入口，所需会话凭证/设备端绑定校验由有限补丁补齐并在 G1 验收，尚非上游默认能力。凭证不进入模型、公共日志或 skills。

同一 Android 实例只建立一个 UiAutomation/Appium 会话服务副屏。用户在主屏的普通触摸和软键盘输入不属于第二个自动化会话；运行期间不能并行启动 `uiautomator dump` 或另一个 UiAutomation instrumentation。

模型只调用 `phone.*`，不能任意执行 Appium 命令、修改 settings、使用旧 `-android uiautomator` 选择器、切换 WebView context 或读全局日志。设备端保持绑定 display/epoch，拒绝非目标窗口节点、失效显示与未绑定请求；电脑端 guard 不能代替这一检查。节点刷新后读取 `node.getWindow().getDisplayId()`；`UiObject2Element.getDisplayId()` 返回构造时缓存值，不能独自证明当前窗口归属。

Observation 包含：`observation_id, session_epoch, display_id, package, activity, windows, frame_id, captured_at, tree_captured_at, frame_captured_at, viewport, rotation, screenshot_ref, tree_ref, semantic_snapshot_ref`。设备端在序列化前过滤非目标 display 的窗口、节点及事件内容；画面取自 scrcpy 绑定副屏。树与帧不是原子快照，分别记录采集时间；窗口/旋转/画面不一致时重新观察。节点 ID 只在对应观察世代有效，不将 Appium 元素缓存当作跨页面或跨恢复的稳定句柄。

新增上传建议使用独立 `InputArtifact`：`artifact_id, source=user_upload, content_hash, mime_type, dimensions, source_message_id?`。上传阶段尚无消息，`source_message_id` 可为空；消息接纳时在 RunStore 建立消息与附件的来源关联，执行器只消费已绑定请求的材料。不可变约束作用于文件内容，不要求上传前先创建业务任务。它没有 display、epoch 或 frame，不能作为 `phone.*` 动作定位的 Observation；图片提取结果只生成业务字段，设备交互另取新观察。

动作请求至少包含 `session_ref, observation_id, target, args, expected_package, expected_precondition`。执行前检查 epoch、App、窗口、旋转和目标新鲜度；页面变化则重新观察并重新定位。坐标以对应截图的尺寸/旋转解释，不能把旧图坐标直接打到新页面。

`phone.set_text` 只针对确认归属副屏、enabled/editable 且 action list 支持 SET_TEXT 的节点，以替换语义写入，再观察字段与焦点。Appium 默认 SendKeys 的追加/clear 路径和特殊尾缀触发全局 Enter 不可直接继承；该版本检测的是字面反斜杠加 n，不能混称普通换行。采用 `mobile:replaceElementValue` 的 `replace=true` 路径，并用有限补丁移除隐式 Enter，按键另走定向通道。尚不支持的文本返回 `UNSUPPORTED_TEXT_INPUT`，不静默改写文本或切换全局 IME/剪贴板。Enter、Back、tap/swipe 首版统一经 scrcpy 绑定显示注入，不启用 Appium 的全局 key/Back 或未核验 W3C actions。

`phone.launch_app` 只接 AppProfile ID，不接任意 Intent URI；执行器构造已测试的定向启动。启动前检查该包在主屏的全部现存 task/activity，包含后台旧任务；没有已验证的独立启动能力则拒绝，不自动迁移或 force-stop。用户在任务期间开始用同包时暂停，副屏销毁不搬回主屏或销毁用户原有 task。

scrcpy 整个运行会话固定 `clipboard_autosync=false`，控制消息白名单拒绝 GET/SET_CLIPBOARD；没有显式剪贴板工具也不意味着后台同步已关闭。`phone.back` 使用定向 `KEYCODE_BACK`，不使用可能在屏灭时触发 POWER 的 `TYPE_BACK_OR_SCREEN_ON`；模型无电源/系统设置操作入口。副屏显示失效或设备锁屏时暂停，不自动唤醒/解锁主屏。

这些 guard 降低错误概率，但不能为未经测试的 App 页面转移提供数学保证。任何主屏跳转都使该测试失败，不能用“立即停机”替代隔离验收。

Appium 启动配置属于可信部署配置，模型不可改写：

- 准备期安装/初始化 instrumentation；任务期固定 `autoLaunch=false`、`noReset=true`、`forceAppLaunch=false`、`shouldTerminateApp=false`、`skipUnlock=true`、`skipLogcatCapture=true`、`disableSuppressAccessibilityService=true`，不在用户使用时执行自动安装、清数据或改系统动画等准备动作。
- 显式管理 `newCommandTimeout` 与会话生命周期。机制探针设为 180 秒，覆盖其 60 秒无副屏命令基线；这不是 HTTP/动作超时。正式运行长时间等待用户时可关闭会话，恢复须重绑和重新观察，不能沿用已过期 session/元素。
- 省略 `hideKeyboard`，禁用 `unicodeKeyboard` 与全局剪贴板工具；`hideKeyboard=false` 仍会重置全局 IME。准备完成后才考虑 `skipDeviceInitialization` 等跳过选项，不能用它们掩盖未完成初始化。
- Gate 关闭时绑定非零 `currentDisplayId`，固定 `enableMultiWindows=true` 并回读核验；全局 Toast 文本采集从 server 启动即禁用，不依赖事后关监听的缓存过期。
- 固定 `waitForIdleTimeout=0`，避免主屏持续产生的无障碍事件使副屏查询等待全局空闲。用副屏明确的前置条件和写后读回决定能否继续；不把关闭 idle 等待理解为所有动作没有超时或目标 App 必然响应。
- Appium 默认 display 为 0，`-1` 可重置设置；server 新会话/重连必须先重新绑定，设备端绑定校验未通过就拒绝观察和动作。旧元素引用随会话世代失效。
- 默认 Appium gesture 注入存在定向设置失败后继续执行的路径；首版复用 scrcpy 的失败即拒绝通道。以后启用 Appium gesture 必须先修该路径和节点窗口为空回落 display 0 的行为，再单独验收。

上述约束与上游固定版本关系见[研究第 7 节](../../research/2026-09-21-agent-runtime-and-gui-research.md#7-复用手机自动化框架与-mcp)，不能用安装最新版代替依赖锁定和运行验收。

### 5.1 模型可读的语义快照

`phone.observe` 默认将副屏树压缩为文本语义快照；图像按任务需要附加，原始 XML/截图仍可作为本地证据引用。模型不必每轮同时接收整棵 XML 和图像。快照至少保留：

- 观察身份及当前 App/窗口；每个节点的临时 `ref`、类型、文本/标签、可用/可编辑/选中状态和允许动作。
- 与决策相关的非交互信息和分组关系，例如商品价格、配送费、会议日期，以及文字归属的列表项。
- 已知缺失区域、截断范围、歧义及覆盖未知提示；树不能完整判定自身遗漏，不把空树解释为无内容或操作成功。

可信适配层保存 `ref → 当前观察中的窗口/节点定位条件/bounds` 映射。模型端 `phone.tap(target.ref)` 与 `phone.set_text(target.ref, text)` 都必须附 `observation_id`；执行前刷新并验证显示、窗口、目标语义和位置，页面改变或匹配不唯一就重新观察。点击沿用 scrcpy 定向通道，不直接映射到任意 Appium click。坐标目标仅在已有对应视觉观察时开放，遵循同样守卫；失效 ref 不自动降级为旧坐标。

`supported_actions` 是设备信息与 Gateway 允许能力的交集。UiAutomator2 的 `includeA11yActionsInPageSource` 默认关闭；候选配置须显式打开并核验输出，或由设备端读取 action list。若拿不到真实 SET_TEXT 能力，返回未知/不支持，不凭 `EditText` 类名宣布可写。这个设置不替代执行时的节点检查。

图片内容、自绘控件、无标签目标或无法通过树消歧时才请求视觉模型；保存触发原因和所用帧。VLM 输出不能绕过 display/epoch 检查，也不能作为全局 IME、剪贴板或无支持文本填写的回退授权。MVP 不开放 WebView context 切换；可调试 DOM 是未来单独验证的观察源。以上为设计契约，语义快照适配器尚未实现。

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

ActionProposal 至少记录 `proposal_id, operation_id, target, canonical_args, canonical_args_hash, task_id, granted_plan_revision, policy_version, evidence_refs`。`canonical_args` 保存供用户审阅的精确参数，按业务包含金额、地址、商品、对象、时间或内容；摘要从同一份参数生成，不只保存无法还原展示内容的 hash。授权绑定这些参数、允许范围和有效期，版本记录其来源。无关 replan、复核价格但金额未变时可重新验证并复用；换地址、换商品或金额/其他条件超出原授权范围时失效，记录覆盖关系的验证结果。首版用当前工具/AppProfile 的少量明确检查实现，不把这些字段扩展成策略语言。

Gateway 在提交前向账本记录 `PREPARED → STARTED`；收到核验依据后登记 `CONFIRMED`，明确未执行为 `FAILED`，提交后超时为 `OUTCOME_UNKNOWN`。核验观察可由 GuiExecutor 或恢复路径请求，操作状态更新仍通过 Gateway/OperationLedger；Coordinator 接纳节点/任务结果，不把一次工具返回直接记成任务成功。同一操作恢复、重复请求及核查复用 operation ID；GUI 没有可靠服务端幂等键，本地 ID 不能消除重复下单风险。

MVP 不自动重试真实业务提交；局部重试预算用于观察/定位等步骤，不含重新点击保存、下单、发送或付款。账本 FAILED 是有证据确认未生效或派发前放弃的终态；确需重做时由新的用户请求明确发起，保留对原失败操作的关联并重新核对实际页面和授权。未知结果不能走这一出口。这样无需首版实现一套提交重试状态机。

核验流程是实际重新打开 App 的列表/详情：日历比较时间、标题和位置；会议比较主题、时间及可见会议号；订单比较商家、商品、总价、地址摘要、创建时段与可见订单标识。日历 UI 不显示 event ID 时，保存可见字段与截图，不伪造系统 event ID。

结果未知时，找到唯一充分匹配才能确认。无匹配、多匹配、读取受限或用户同时修改都不能作为自动再点提交的理由。保留待人工核查状态。取消尚未执行的节点立即生效；取消已经发生的业务是新任务，不自动删除会议、清空用户原有购物车或退款。

interrupt 在独立审阅节点，节点前只做可重放的准备工作。恢复使用相同 thread 与 `Command(resume=...)`；新任务输入用正常 state 输入，不把 resume 当万能更新方式。MVP 只允许安全继续执行，不提供会重放真实提交动作的任意 time-travel 按钮。

## 8. 消息、Redis 与 checkpoint

LangChain 消息保留类型、ID、内容块、`AIMessage.tool_calls` 和 `ToolMessage.tool_call_id`。工具调用组完整进入或离开上下文；大截图和树放 artifact，Redis 存引用；本次视觉调用由适配器加载必要截图为实际图像内容块，不重复附带全部历史图像。`add_messages` 按 ID 合并，不是内容去重器。

上下文由系统约束、选中 skills、规范化请求、结构化任务状态、必要摘要、最近完整消息组和当前观察构成。先预算 token，再压缩历史；不能压缩掉仍有效的预算、禁忌、授权和未完成 tool call。

Redis 使用列表/哈希/集合等基本命令封装 `append_once(message_id)`；写入顺序和去重操作应原子执行。历史保留策略先不自动过期，使用持久 volume 和明确的 Redis 持久化配置；清理接口保留，截图另行设本地保留期限。

未完成、暂停和结果未知任务仍引用的用户输入图不因缓存期限到期删除；恢复时检查文件存在及摘要一致，缺失/损坏时保持受阻并请求补充材料，不用聊天摘要冒充原图。

SQLite RunStore 持久保存已接收请求、权威计划版本、操作账本及待投递对话事件。Redis 是会话历史查询层，投递按稳定 message ID 去重；暂时不可用时重试补齐，不伪造已同步。checkpoint 保存可对账的执行游标，账本是副作用恢复依据；每次恢复都先核对 RunStore，不能用旧 checkpoint 覆盖已接纳的新计划。即使用同一 SQLite 文件，也不假设框架 checkpoint、账本和 Android 点击构成原子事务。

单进程按 task/device 加锁，graph state 单一写者。未来替换 RedisSaver/Postgres 或增加多个 worker 时，要新增分布式所有权、租约与 fencing，本版不提前实现。
