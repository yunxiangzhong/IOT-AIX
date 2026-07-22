# AIX PC 服务与上位机

本目录包含 PySide6 上位机和其启动脚本。它消费 PC 主动帧服务，不再从 ESP 拉取 capture.jpg，也不会在 UI 内执行同步模型推理。当前界面为“中控总览 / 协同场景”双页：默认用稳定的已分析画面，设备接入放在顶层入口；气动标定页仍只是受限命令转发，且本项目没有真实泵、阀和气囊的验收记录。

## 已实现的功能

| 功能 | 已实现内容 | 当前边界 |
| --- | --- | --- |
| 视觉闭环展示 | 原子显示 PC 服务的已分析帧、YOLO 检测框、稳定风险、上传/推理/回调延迟和 RGB 确认 | 画面约 1 秒更新一次，不宣称实时；展示的是原型视觉风险，不是安全判断 |
| 中控总览 | 集中展示 OV5640、MPU6050、压力传感器、DFPlayer、RGB、泵/阀状态、实时数据、推导与执行结果；18 张映射卡绑定唯一权威事件源，相同内容不重复刷新 | 已分析画面按模型处理速率更新；卡片状态来自软件协议和测试数据时，不可当作实物安全证据 |
| 状态趋势 | 可点击查看最近 60 秒的 OV5640 上传速率、视觉风险、MPU6050 加速度/倾角和压力变化，支持暂停与当前/最小/最大值 | 趋势只反映上位机收到的样本；缺帧、断链或未标定传感器会直接影响结果 |
| PC 视觉语音策略 | attention/high/critical 生成 `voice_prompt` 曲目 1/2/3，保持命令编号幂等、同级冷却并在升级时立即提示 | 已由 COM21 的 `voice_status.ready`、曲目 1–3 的 `playing`/`finished` 和实际听音交叉确认；不代表整机、气动或安全验收 |
| 串口遥测 | 解析并记录 pressure、motion v2、camera_status、action_status、pneumatic_status、hardware_health | COM21 已回传 `vision_critical` 时的泵开、阀通电和有效压力；泵阀没有独立电流或位置回读，气路性能仍需单独验收 |
| 气动标定页 | 读取配置、保存释放阈值、发送泵阀自检/短充气脉冲/泄压/急停/故障复位，并显示返回状态 | UI 不能开启自动模式，不能跳过 ESP 的 token、压力、时长或故障保护 |
| 碰撞求助记录 | 新 MPU 碰撞在本地打开静默、持续的求助窗口，并将状态变化写入 `collision_events.jsonl` | 不调用外部救援；窗口、日志和自动化测试都不是实体气囊验收 |
| PC 气动代理 | PC 服务以最近上传帧的来源 IP 转发到 ESP :8080，而不是由 UI 填写 ESP 地址 | 没有最近设备帧、token 不匹配或 ESP 控制关闭时，命令会失败/被拒绝 |
| 会话记录 | 自动保存帧、视觉、遥测、动作、气动命令与配置 | 文件记录不是实物安全验收报告 |
| 路侧协同场景 | L 形路口画布展示右侧盲区货车 ETA 5 秒、下方骑行者、摄像头视场与链路；倒计时结束前，骑行者从 18 km/h 降至 6 km/h | 路侧检测、货车画面和 ETA 都是模拟输入；演示响应在约 2.3 秒显示，真实 `road_hazard_ack` 到达时会覆盖它；货车在 0 秒停在停止线而非通过路口 |
| UI 测试 | 上位机组件、串口解析、气动协议、会话记录、18 张卡片唯一所有者和重复刷新抑制均有主机侧自动化测试覆盖 | 测试数据不驱动真实 GPIO 或负载 |

## 数据源与默认页面

- PC HTTP：/healthz、/v1/frame/processed.jpg、/v1/state/latest、/v1/pneumatic/config、/v1/pneumatic/command；latest.jpg 仅作原图诊断。
- ESP 串口：pressure、motion、camera_status、action_status、pneumatic_status。
- ESP 串口还会记录 `voice_status` 和 `road_hazard_status`；远端货车事件的真实固件动作仅为 RGB 仲裁，界面的语音/保护状态不会伪装为 DFPlayer 播放或气囊充气证据。
- 默认页用固定已分析画面和中文交通目标框，静态展示默认开启；风险卡只接受同一帧 PC 快照，串口 `action_status` 只写诊断日志，不再覆盖风险、动作反馈或 RGB 卡。气动控制放在诊断/标定区域，不与默认视觉提示混为“已自动保护”。
- 设备首次上报新的 boot_id 后，上位机才请求该设备的气动配置。

PC 服务的气动代理会把请求转到最近一帧来源地址的 ESP 端口 8080。ESP 仍是最终裁决者：气动标定默认目标/上限/最大充气为 `8 kPa` / `12 kPa` / `5000 ms`；XGZP6847A 的测量量程仍为 `200 kPa`，但软件控制硬上限为 `20 kPa`。UI 不能改变自动开关，也不能跳过压力、硬上限、泵阀自检或故障保护。

新 MPU 碰撞仅在相邻样本 `Δ|a|≥1.2 g` 且 `0<dt≤20 ms` 时成立，`200 ms` 不应期将同一次振铃合并。它的气动共同门不依赖视觉新鲜度；rapid tilt 仅作诊断，不会充气。旧 legacy impact 仅作兼容解析/展示，不会生成新碰撞告警、求助窗口或充气请求。

## 状态卡刷新规则

- “感知与外设”六张卡只接收 `hardware_health`，普通压力、相机、运动、语音或气动采样不能反向改写硬件健康结论。
- “实时数据”六张卡分别由统一视觉链路、motion、pressure、voice、统一 RGB 链路和 pneumatic 状态负责；“推导与执行”六张卡同样各有唯一所有者。
- `/healthz` 仅在首个统一链路状态到达前提供模型占位信息；已有风险结果后，周期健康轮询不能把页面重置为“等待视觉帧”。
- 每次更新同时比较显示文案和状态色调。内容未变化时不会进入 500 ms 合并刷新队列；故障等紧急状态可立即显示，真实数值、帧号或状态发生变化时才更新。
- 上述规则已有跨事件源覆盖、全部 18 张卡唯一所有者和相同内容去重测试；尚未用整机长时间运行证明所有外部数据源永不抖动。

## 哪些内容是模拟或兼容用途

- 生产上位机已移除模拟数据源；串口接入会自动识别 CP210x 设备并在断开后重连。
- HTTP、串口和气动相关的自动化测试使用测试夹具/模拟传输；通过测试或源码构建不代表 MOSFET、SS54、泵、阀、电池、气囊已工作，更不构成实体气囊验收。
- camera_preview 和 vision_depth 仍可被解析，用于旧记录或诊断兼容；默认界面的帧源始终是 PC 主动帧服务。
- 旧 /v1/infer 与 /v1/analyze 仅供兼容测试，不是启动器运行的默认链路。
- 协同场景中的路侧相机、云端货车检测、ETA、演示响应和骑行者减速均为软件演示。真实 ACK、串口状态和会话记录会如实显示，但不构成真实交通监控、语音或气动验收。

## 尚未实现或尚未验收

- 没有实机证明 UI 气动命令能驱动泵或阀；当前默认固件会拒绝这类命令。
- MPU6050 已完成 COM21 的基础频率读数；仍没有气囊压力标定、三通阀断电泄压或 SS54 反电动势保护的验收数据。
- 没有完成自动触发、断网、模型失效、压力无效、急停和长时间运行的整机测试。
- DFPlayer 的曲目 1–3 已完成 COM21 串口和实际听音验证；尚未完成风险升级中断、10 分钟整机长稳，或与气动/安全相关的验收。
- 上位机不是安全控制器，也不能把视觉风险或模拟压力数据解释为安全指令。

## 会话内容

收到链路或串口数据后自动创建会话，按帧号去重保存：

~~~text
frames/
vision.ndjson
telemetry.ndjson
action.ndjson
pneumatic.ndjson
road_hazard.ndjson
collision_events.jsonl
pressure.csv
model.log
session.json
~~~

pneumatic.ndjson 记录已发送命令、ESP 返回确认和气动状态；session.json 记录读取到的气动配置。它们用于追溯软件链路，并不能替代万用表、压力表或气路测试。

road_hazard.ndjson 记录路侧事件提交、服务状态推进、真实 ACK 与串口 `road_hazard_status`。模拟页面不能制造 ESP32 成功；设备离线、地址缺失、boot 不匹配、TTL 到期和 ACK 不匹配会在服务状态中保留实际失败原因。

collision_events.jsonl 记录新 MPU 碰撞的本地求助窗口和气动共同门状态；它用于软件追溯，不是实物气囊或外部救援完成记录。

## 启动

唯一推荐入口：

~~~powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\start_host_app.cmd
~~~

启动器会同步运行时配置、检查 2.4 GHz 热点、复用已有的健康模型服务或启动异步模型服务、等待 HTTP 健康状态，再启动 UI。旧 run_host_app.cmd 不是当前链路入口。

运行时 Wi-Fi、token、串口、存储路径和模拟开关都在本机配置中；凭据与 token 不会提交到 Git。

## 验证与相关文档

~~~powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
~~~

- [仓库总览](../README.md)：跨模块的已实现、模拟、未完成和默认安全配置。
- [固件说明](../AIX/README.md)：固件 Kconfig 开关、接口与实物边界。
- [DFPlayer 语音接线与验收](../docs/hardware/dfplayer-voice-wiring.md)：唯一的 DFPlayer 接线、TF 卡、供电与后续验收说明。
- [气泵、三通电磁阀与 MPU6050 接线说明](../docs/hardware/pneumatic-mpu6050-wiring.md)：接线、气路和验收顺序。
