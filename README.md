# AIX 主动视觉头盔原型

这是一个仍在原型阶段的 ESP32-S3 / PC 协同项目。当前默认链路是“相机采集、PC 视觉推理、ESP 回调校验、RGB 提示”；气泵、电磁阀和 MPU6050 的软件支持已经合入源码，但尚未完成实物接线和整机验收。

~~~text
OV5640 → ESP32-S3 主动上传 JPEG → PC 最新帧缓存 / DA3 + SSDLite 推理
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
| PC DA3 + SSDLite 最新帧推理、/risk 回调、TTL/帧序/token 校验 | 已实现并有主机侧测试 | 输出仅为相对视觉风险，不是距离、碰撞概率或安全结论 |
| GPIO38 RGB 和 action_status | 已实现并构建通过 | 仅作原型语义提示，不是安全执行器 |
| DFPlayer 视觉风险语音提示 | `/risk.voice_prompt`、UART2 DFPlayer 驱动、三级曲目映射、去重与主机侧测试已实现 | 已在 COM21 看到 `voice_status` 的 `ready`、曲目 1–3 的 `playing`/`finished`，并由实际听音确认；未完成 10 分钟整机/气动/安全验收，语音仅为原型提示 |
| 压力遥测 | 固件采集、串口协议和上位机记录已实现 | 仍需在最终气路上标定；旧的 180 kPa 是传感器诊断阈值，不是气囊控制目标 |
| MPU6050 与运动检测 | I2C 驱动、motion v2、运动检测及 C 测试已实现 | 模块尚未完成接线与现场动作阈值标定 |
| 气泵 / 三通电磁阀控制 | GPIO40 / GPIO41、手动脉冲、急停、泄压、压力/超时故障保护、策略测试和固件编译已实现 | MOSFET、两个 SS54、泵、阀、电池和气囊均未在本仓库记录中完成实物验收 |
| 自动充气 | 策略代码已实现 | 默认关闭，且上位机不能开启；未完成实物标定前不得启用 |
| PySide6 上位机气动标定页 | 状态显示、配置读取、手动命令、会话记录已实现并有主机测试 | 页面不能绕过固件安全限制，也不代表已驱动真实负载 |

## 默认安全配置

AIX/sdkconfig.defaults 中：

~~~text
CONFIG_AIX_ENABLE_PNEUMATIC_CONTROL=n
CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC=n
~~~

因此，当前默认构建不会让 GPIO40 / GPIO41 驱动泵或阀，也不会根据视觉或加速度自动充气。若将来接入硬件，必须先按接线说明仅开启“控制硬件”，保持自动模式关闭，并按验收步骤逐项测试；详见 [气泵、三通电磁阀与 MPU6050 接线说明](docs/hardware/pneumatic-mpu6050-wiring.md)。

## 哪些内容是模拟或兼容用途

- 上位机“模拟数据”开关只生成**模拟压力样本**，用于验证 UI、会话记录和显示流程；它不会生成真实 MPU6050 数据、不会调用气动命令、更不会驱动 GPIO。
- 自动化测试中的 HTTP、串口和气动输入是测试夹具/模拟数据。测试通过和固件能编译，不能替代泵、阀、气路、二极管、电池与压力传感器的通电测试。
- 旧的 /v1/infer、/v1/analyze、camera_preview、vision_depth 解析能力仅为兼容或诊断保留，不是当前默认视觉链路。

## 尚未实现或尚未验收

- 没有完成“视觉风险 / MPU 事件 → 自动充气”的实物联调。
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
- GET /v1/frame/latest.jpg?device_id=aix-helmet-01：读取最新上传帧。
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
- [host_app/README.md](host_app/README.md)：PC 服务、上位机、模拟数据和会话记录。
- [docs/hardware/pneumatic-mpu6050-wiring.md](docs/hardware/pneumatic-mpu6050-wiring.md)：MOSFET、SS54、泵、阀、电池与 MPU6050 的接线及验收顺序。
- [docs/hardware/dfplayer-voice-wiring.md](docs/hardware/dfplayer-voice-wiring.md)：DFPlayer Mini、UART2、8 Ω 喇叭、TF 卡、供电和语音验收步骤。
