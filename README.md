# AIX 主动视觉头盔原型

这是一个仍在原型阶段的 ESP32-S3 / PC 协同项目。当前默认链路是“相机采集、PC 视觉推理、ESP 回调校验、RGB 提示”；上位机还提供“右侧货车 5 秒后到达路口”的协同预警演示。气泵、电磁阀和气囊尚未完成实物气路验收，不能作为人身安全保护装置。

~~~text
OV5640 → ESP32-S3 每 1000 ms 上传最新 JPEG → PC 已处理快照 / DA3 + YOLO26m 推理
        → PC 回调 vision_risk → ESP action_policy → GPIO38 板载 RGB
        → action_ack + 串口 action_status → PySide6 上位机
        └→ /risk.voice_prompt → UART2 DFPlayer Mini → SPK1/SPK2 8 Ω 喇叭

MPU6050 / 压力遥测 → 气动安全策略 → GPIO40 气泵 MOSFET、GPIO41 电磁阀 MOSFET
                                      （默认构建关闭，未接入实物时不会输出控制）
~~~

## 当前状态（以代码和实际验收分别说明）

| 模块 | 源码与自动化验证 | 实机状态 / 边界 |
| --- | --- | --- |
| OV5640 QVGA/JPEG 采集、失败恢复、PC 主动上传 | 已实现；主机测试和 ESP-IDF 全量构建通过 | 已有 OV5640 跑通记录；仍未完成本版本的 10 分钟整机闭环验收 |
| PC DA3 + YOLO26m 交通目标推理、/risk 回调、TTL/帧序/token 校验 | 已实现并有主机侧测试；RTX 4060 上使用 CUDA FP16 | 输出仅为相对视觉风险，不是距离、碰撞概率或安全结论；Ultralytics 有 AGPL-3.0 许可边界 |
| 上位机中控总览与协同场景 | Apple 浅色双页界面、顶层设备接入、诊断/标定入口、稳定画面模式、状态趋势与路口模拟已实现；18 张映射卡采用唯一权威数据源和内容去重，当前验证的 127 项主机侧测试通过 | 默认显示固定已分析画面；状态卡不会被健康心跳、普通采样和串口诊断轮流覆盖，但这些软件约束不等于实机安全验收 |
| 路侧货车协同预警 | ESP32 `/road-hazard` 校验、幂等 ACK、TTL、RGB 仲裁和 PC 会话记录已实现 | 路侧相机、云端识别与 ETA 在本 Demo 中为模拟输入；当前固件对路侧事件只仲裁 RGB，不会由此触发 DFPlayer 或气动控制 |
| GPIO38 RGB 和 action_status | 已实现并构建通过 | 仅作原型语义提示，不是安全执行器 |
| DFPlayer 视觉风险语音提示 | `/risk.voice_prompt`、UART2 DFPlayer 驱动、三级曲目映射、去重与主机侧测试已实现 | 已在 COM21 看到 `voice_status` 的 `ready`、曲目 1–3 的 `playing`/`finished`，并由实际听音确认；未完成 10 分钟整机/气动/安全验收，语音仅为原型提示 |
| 压力遥测 | 固件采集、串口协议、上位机记录与阈值泄压策略已实现 | XGZP6847A 的测量量程仍为 200 kPa；软件控制硬上限固定为 20 kPa，默认目标/上限为 8/12 kPa |
| MPU6050 与运动检测 | I2C 驱动、motion v2、相邻样本 Δ\|a\| 碰撞检测及 C 测试已实现 | 仅 Δ\|a\|≥1.2 g 且 0<dt≤20 ms 触发新碰撞；200 ms 不应期合并同一次振铃，rapid tilt 仅作诊断；仍缺少佩戴状态的静置校准和误报率验收 |
| 气泵 / 三通电磁阀控制 | GPIO40 / GPIO41、压力阈值泄压、泵阀自检、手动脉冲、急停、泄压、压力/超硬上限故障保护、策略测试和固件编译已实现 | COM21 串口已回传 `vision_critical` 下的泵开、阀通电和有效压力；没有独立泵/阀电流或位置传感器，不能据此宣称气路性能已验收 |
| 自动充气 | 有效 PC 视觉 `HIGH/CRITICAL` 或新 MPU 碰撞可进入策略；两者均须通过自动开关、压力新鲜、泵阀自检和故障锁止共同门 | rapid tilt 不会充气；上位机不能更改 ESP32 的自动开关、阈值、硬上限或故障保护 |
| PySide6 上位机气动标定页 | 状态显示、配置读取、手动命令、会话记录已实现并有主机测试 | 页面不能绕过固件安全限制，也不代表已驱动真实负载 |

## 默认安全配置

AIX/sdkconfig.defaults 中：

~~~text
CONFIG_AIX_ENABLE_PNEUMATIC_CONTROL=n
CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC=n
~~~

因此，当前默认构建不会让 GPIO40 / GPIO41 驱动泵或阀，也不会根据视觉或加速度自动充气。若将来接入硬件，必须先按接线说明仅开启“控制硬件”，保持自动模式关闭，并按验收步骤逐项测试；详见 [气泵、三通电磁阀与 MPU6050 接线说明](docs/hardware/pneumatic-mpu6050-wiring.md)。

软件默认标定为目标 `8 kPa`、控制硬上限 `12 kPa`、最大充气 `5000 ms`；无论 XGZP6847A 的 `200 kPa` 测量量程如何，软件控制硬上限不得超过 `20 kPa`。碰撞仅采用新规则：相邻样本 `Δ|a|≥1.2 g` 且 `0<dt≤20 ms`，`200 ms` 不应期内的振铃合并为同一事件；rapid tilt 仅用于诊断，不是充气依据。

## 哪些内容是模拟或兼容用途

- 生产上位机已移除模拟压力数据源，只接收真实串口；自动化测试中的数据不进入生产链路。
- 自动化测试中的 HTTP、串口和气动输入是测试夹具/模拟数据。测试通过和固件能编译，不能替代泵、阀、气路、二极管、电池与压力传感器的通电测试。
- 旧版 legacy `impact` 事件仅为兼容解析和展示保留；它不产生新的碰撞告警，也不是气囊充气依据。
- 旧的 /v1/infer、/v1/analyze、camera_preview、vision_depth 解析能力仅为兼容或诊断保留，不是当前默认视觉链路。
- 上位机把 `hardware_health`、实时传感器值、统一视觉链路状态和气动反馈分配给各自固定的展示卡；`/healthz` 只负责首个链路状态到达前的占位，串口 `action_status` 只作诊断记录。相同文案和色调不会重复进入 500 ms UI 刷新队列。

## 7.19 Demo：路口协同预警

上位机的“协同场景”页演示一名骑行者从下方接近十字路口、右侧盲区货车预计 5 秒后刚好到达停止线的流程：

1. 以固定场景画布表示路侧摄像头发现货车，PC/云端链路生成 ETA 事件。
2. 上位机提交 `truck_right_eta_5s` 协同事件，并展示摄像头、云端、ESP32 的链路状态。
3. 演示模式在倒计时结束前显示语音/保护动作已响应，骑行者速度从 18 km/h 降至 6 km/h；真实 ESP32 ACK 到达时会覆盖演示状态。
4. 倒计时到 0 时货车停在路口停止线，不表示已经通过路口。

这是一段可重复播放的软件演示：路侧画面、云端识别、ETA、语音/保护动作状态均不能视为真实交通监控、真实播音或气囊充气证据。

## 尚未实现或尚未验收

- 没有完成“视觉风险 / MPU 事件 → 自动充气”的实物联调。
- 新碰撞触发后，上位机只在本地打开静默且持续的求助窗口，并记录 `collision_events.jsonl`；这不是呼叫外部救援，也不能视为气囊或人身保护验收。
- 没有气囊目标压力、硬上限、泵的启动/堵转电流、气阀方向和断电泄压的现场标定记录。
- 没有 10 分钟持续运行、断网、模型停机、传感器失效、急停后的实机安全验收。
- 未接入蜂鸣器、振动马达、医疗级传感器或认证级安全硬件。本项目不是医疗设备，也不能作为人身安全防护装置使用。
- DFPlayer 已完成曲目 1–3 的 COM21 串口与实际听音验证；尚未完成与相机、Wi-Fi、推理协同的 10 分钟长稳、风险升级中断，以及任何气动或安全验收。即使后续完成，语音也不是碰撞预警、人身安全或医疗级保障。

## 启动与接口

推荐从上位机启动器进入默认视觉链路：

~~~powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\start_host_app.cmd
~~~

启动器同步本机运行时配置、检查热点、启动 0.0.0.0:8008 的异步模型服务，等待 /healthz 后启动 PySide6 界面。Wi-Fi 凭据、token 和 sdkconfig.runtime 均不提交 Git。

PC 服务主要接口：

- POST /v1/frames：ESP 上传 JPEG，成功返回 frame_ack（HTTP 202）。
- GET /healthz：HTTP、模型加载、GPU 和错误状态。
- GET /v1/frame/latest.jpg?device_id=aix-helmet-01：读取最新上传原图，仅用于诊断。
- GET /v1/frame/processed.jpg?device_id=aix-helmet-01：读取与风险结果同一 frame_seq 的已分析画面，供上位机稳定展示。
- GET /v1/state/latest?device_id=aix-helmet-01：查看上传、推理、回调和 RGB 确认的统一状态。
- ESP 在本地 :8080 提供 /risk、/pneumatic/config、/pneumatic/command；气动控制默认关闭时命令会被拒绝。
- `/risk` 可选携带 `voice_prompt: {"command_id":"<boot_id>:<frame_seq>:<track>","track":1|2|3}`；仅在既有 token、设备、boot、帧序和 TTL 校验通过后才会交给 DFPlayer。attention/high/critical 对应 0001/0002/0003，low 不发送语音。
- `action_ack.voice_ack` 返回语音是否 `queued`、`duplicate`、`suppressed`、`rejected` 或 `unavailable`；串口 `voice_status` 记录 `initializing`、`ready`、`playing`、`finished`、`error` 与曲目、帧序、命令编号。

## 验证与构建

~~~powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BuildFirmware
~~~

-BuildFirmware 会在 ESP-IDF 环境中执行全量构建，并在 AIX/build-verify/ 生成不含 token 的 firmware-manifest.json。这验证的是源代码和构建产物；不等同于实物驱动验收。

## 分目录说明

- [AIX/README.md](AIX/README.md)：ESP32-S3 固件、配置开关、气动安全边界和烧录前检查。
- [host_app/README.md](host_app/README.md)：PC 服务、真实串口上位机和会话记录。
- [docs/hardware/pneumatic-mpu6050-wiring.md](docs/hardware/pneumatic-mpu6050-wiring.md)：MOSFET、SS54、泵、阀、电池与 MPU6050 的接线及验收顺序。
- [docs/hardware/dfplayer-voice-wiring.md](docs/hardware/dfplayer-voice-wiring.md)：DFPlayer Mini、UART2、8 Ω 喇叭、TF 卡、供电和语音验收步骤。
