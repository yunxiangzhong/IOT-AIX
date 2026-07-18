# AIX ESP32-S3 固件

目标板为 ESP32-S3-DevKitC-1 v1.1。固件默认运行 OV5640 主动上传、PC 风险回调校验和 GPIO38 RGB 提示；气动执行器硬件与自动模式在默认构建中均关闭。

## 已实现的固件功能

| 功能 | 当前代码状态 | 注意事项 |
| --- | --- | --- |
| OV5640 320×240 JPEG 采集、失败恢复、约 5 FPS | 已实现 | 采集到的最新 JPEG 每 400 ms 上传给 PC |
| Wi-Fi、设备标识、token、PC 上传和风险回调 | 已实现 | /risk 对 device、boot_id、帧序、TTL、分数和等级做校验 |
| RGB 与 action_status | 已实现 | GPIO38 最大亮度 20%，只表示原型状态 |
| DFPlayer Mini 视觉风险语音 | UART2 驱动、三级 `/mp3/0001.mp3` 至 `0003.mp3` 映射、命令去重和 `voice_status` 已实现 | 仅接收已通过 `/risk` 校验的 PC 视觉风险；COM21 已记录 `ready`、曲目 1–3 的 `playing`/`finished`，且实际听音确认；未完成 10 分钟整机/气动/安全验收 |
| XGZP6847A 压力遥测 | 已实现 | 用于遥测和气动策略的输入有效性检查，最终气路仍需标定 |
| MPU6050 | I2C 驱动、motion v2 串口事件、运动检测与 C 测试已实现 | 未完成实物模块接线、静置校准和现场阈值验证 |
| 气泵 / 三通电磁阀 | GPIO40、GPIO41、手动脉冲、泄压、急停、故障锁存与策略测试已实现 | 默认不初始化输出控制；没有实物负载验收 |
| 自动充气条件 | 视觉 HIGH/CRITICAL 或 MPU impact/rapid_tilt 的策略代码已实现 | 必须由编译配置明确开启，默认关闭，不能由上位机打开 |

## 气动相关的安全默认值

sdkconfig.defaults 固定为：

~~~text
CONFIG_AIX_ENABLE_PNEUMATIC_CONTROL=n
CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC=n
~~~

这表示默认烧录产物不会驱动 GPIO40 气泵 MOSFET 或 GPIO41 电磁阀 MOSFET。即使 PC 发出气动请求，控制关闭时也会拒绝命令；上位机也没有打开自动模式的入口。

将来接入硬件时，先只启用 CONFIG_AIX_ENABLE_PNEUMATIC_CONTROL=y，保持 CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC=n，并严格遵循 [气泵、三通电磁阀与 MPU6050 接线说明](../docs/hardware/pneumatic-mpu6050-wiring.md) 的“断开负载 → 测信号输出 → 接阀 → 短脉冲 → 接气囊”顺序。

气动策略仅在保存受限标定值后才可运行。压力无效、压力超过 200 ms 未刷新、超过硬上限、充气/保压超时或急停时，固件进入 fault_vent：关闭泵与电磁阀，使所给三通阀按断电气路泄压。该设计和单元测试不等同于真实气路的安全认证。

## 引脚与实物边界

| 对象 | 固件引脚 | 实物状态 |
| --- | --- | --- |
| 板载 RGB | GPIO38 | 已用于视觉原型提示 |
| 气泵 MOSFET 输入 | GPIO40 | 已在源码中定义；未接入泵、MOSFET、SS54 与电池测试 |
| 电磁阀 MOSFET 输入 | GPIO41 | 已在源码中定义；未接入阀、MOSFET、SS54 与电池测试 |
| MPU6050 SDA / SCL / INT | GPIO2 / GPIO6 / GPIO39 | 已在源码中定义；未接入 MPU6050 实测 |

泵和阀必须使用独立的 5–6V 电池组或外部电源，不能由开发板 5V 引脚供电；两块 MOSFET 的信号地、ESP32 GND 和电源负极必须共地。每个泵/阀负载各需要一个 SS54 反向并联。完整接线、气阀 1/2/3 气口和上电验收见上述接线文档。

DFPlayer 的 UART2 引脚、供电、TF 卡、喇叭、音频命名、排障和后续验收只以 [DFPlayer Mini 视觉风险语音接线与验收](../docs/hardware/dfplayer-voice-wiring.md) 为准。

## 串口与 HTTP 协议

- 串口状态包括 pressure、motion v2、camera_status、action_status 和 pneumatic_status。
- ESP 在端口 8080 接收 PC 的 /risk，并提供 /pneumatic/config 与 /pneumatic/command。
- `/risk` 保持 `version: 1`，可附带 `voice_prompt`：`{"command_id":"<boot_id>:<frame_seq>:<track>","track":1|2|3}`。固件仅在现有 token、device_id、boot_id、帧序和 TTL 校验都通过后接收该字段；attention/high/critical 必须分别匹配 track 1/2/3，low 不播报。
- `action_ack` 新增 `voice_ack`，其中 `queued` 表示已入队、`duplicate` 表示同一 command_id 的 HTTP 重试被缓存确认且不会二次播音、`suppressed` 表示高风险语音仍在播放、`rejected` 表示字段无效、`unavailable` 表示 TF/模块未就绪。风险回调本身仍可成功，即使语音模块暂时不可用。
- 新增串口 `voice_status`：`initializing / ready / playing / finished / error`，含 track、frame_seq、command_id 和 error，便于上位机/串口记录诊断。
- /pneumatic/command 仅支持受限的短充气脉冲、泄压、急停、故障复位和保存标定；它不允许 PC 直接解除固件的压力、时间和故障限制。
- camera_preview 仅为显式启用的诊断兼容模块；默认视觉路径不是 PC 拉取 ESP 的 /capture.jpg。

## 运行时配置

在仓库根目录执行：

~~~powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\AIX\sync_runtime_config.ps1
~~~

该脚本创建被 Git 忽略的 sdkconfig.runtime，首次可迁移旧 sdkconfig.preview 的 Wi-Fi 凭据，并设置设备 ID、随机 link token、PC 服务 URL、上传周期、风险端口、预览和 RGB 等配置。凭据、token 和运行时配置均不提交 Git。

DFPlayer 的构建开关位于 Kconfig：

~~~text
CONFIG_AIX_ENABLE_VOICE_PROMPT=y
CONFIG_AIX_VOICE_VOLUME=18
~~~

音频文件、TF 卡约束和默认曲目内容见唯一的 [DFPlayer 接线与验收文档](../docs/hardware/dfplayer-voice-wiring.md)。

## 构建与烧录

推荐从仓库根目录验证：

~~~powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BuildFirmware
~~~

该命令会进入 ESP-IDF 环境、执行 C 安全测试、全量构建，并输出 AIX/build-verify/firmware-manifest.json。通过构建只说明源码可生成固件，不说明连接到泵、阀、气囊或 MPU6050 后可安全运行。

在完成接线检查、默认低电平测量和人工短脉冲验收后，才可使用：

~~~powershell
idf.py -p COMxx flash monitor
~~~

DFPlayer 已完成的实机证据仅限 COM21 上的 `voice_status.ready`、曲目 1–3 的 `playing`/`finished` 串口日志及实际听音；后续接线、验收与安全边界见唯一的 [DFPlayer 接线与验收文档](../docs/hardware/dfplayer-voice-wiring.md)。

## 尚未完成的工作

- 未记录气泵、电磁阀、两个 SS54、电池、气囊和压力传感器在同一气路上的通电验收。
- 未完成 MPU6050 的实机校准、跌落/冲击误报率测试或与视觉风险的联调。
- 未完成自动模式、断网、模型失效、传感器异常、急停和长时间运行的整机安全验收。
- DFPlayer 已完成曲目 1–3 播放的串口和听音验证；尚未完成风险升级中断、长稳运行，以及任何气动或安全验收。语音提示不得当作人身安全保证。
- 本固件不是医疗器械或认证级安全控制系统，不可用于人身安全防护。
