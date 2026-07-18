# AIX PC 服务与上位机

本目录包含 PySide6 上位机和其启动脚本。它消费 PC 主动帧服务，不再从 ESP 拉取 capture.jpg，也不会在 UI 内执行同步模型推理。气动标定页已实现，但它只是经 PC 服务转发受限命令；默认固件关闭气动控制，且本项目还没有真实泵、阀和气囊的验收记录。

## 已实现的功能

| 功能 | 已实现内容 | 当前边界 |
| --- | --- | --- |
| 视觉闭环展示 | 显示 PC 服务的最新帧、风险、上传/推理/回调延迟和 RGB 确认 | 展示的是原型视觉风险，不是安全判断 |
| PC 视觉语音策略 | attention/high/critical 生成 `voice_prompt` 曲目 1/2/3，保持命令编号幂等、同级冷却并在升级时立即提示 | 已由 COM21 的 `voice_status.ready`、曲目 1–3 的 `playing`/`finished` 和实际听音交叉确认；不代表整机、气动或安全验收 |
| 串口遥测 | 解析并记录 pressure、motion v2、camera_status、action_status、pneumatic_status | 新增的 MPU6050 与气动硬件尚未实机接线验证 |
| 气动标定页 | 读取配置、发送短充气脉冲/泄压/急停/故障复位/保存限制，并显示返回状态 | UI 不能开启自动模式，不能跳过 ESP 的 token、压力、时长或故障保护 |
| PC 气动代理 | PC 服务以最近上传帧的来源 IP 转发到 ESP :8080，而不是由 UI 填写 ESP 地址 | 没有最近设备帧、token 不匹配或 ESP 控制关闭时，命令会失败/被拒绝 |
| 会话记录 | 自动保存帧、视觉、遥测、动作、气动命令与配置 | 文件记录不是实物安全验收报告 |
| UI 测试 | 上位机组件、串口解析、气动协议和会话记录有主机侧测试 | 测试数据不驱动真实 GPIO 或负载 |

## 数据源与默认页面

- PC HTTP：/healthz、/v1/frame/latest.jpg、/v1/state/latest、/v1/pneumatic/config、/v1/pneumatic/command。
- ESP 串口：pressure、motion、camera_status、action_status、pneumatic_status。
- 默认页展示相机、视觉风险与 RGB 链路；气动控制放在诊断/标定区域，不与默认视觉提示混为“已自动保护”。
- 设备首次上报新的 boot_id 后，上位机才请求该设备的气动配置。

PC 服务的气动代理会把请求转到最近一帧来源地址的 ESP 端口 8080。ESP 仍是最终裁决者：只有编译时启用了气动控制时，才可能接受受限命令；自动模式默认关闭，UI 没有开启它的能力。

## 哪些内容是模拟或兼容用途

- 设置中的“模拟数据”只会生成模拟压力样本，用于验证界面、图表和会话记录。启用模拟后不会伪造 MPU6050 事件、不会调用 PC 气动代理，也不会触发 GPIO。
- HTTP、串口和气动相关的自动化测试使用测试夹具/模拟传输；通过测试不代表 MOSFET、SS54、泵、阀、电池、气囊已工作。
- camera_preview 和 vision_depth 仍可被解析，用于旧记录或诊断兼容；默认界面的帧源始终是 PC 主动帧服务。
- 旧 /v1/infer 与 /v1/analyze 仅供兼容测试，不是启动器运行的默认链路。

## 尚未实现或尚未验收

- 没有实机证明 UI 气动命令能驱动泵或阀；当前默认固件会拒绝这类命令。
- 没有 MPU6050 的串口实测、气囊压力标定、三通阀断电泄压或 SS54 反电动势保护的验收数据。
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
pressure.csv
model.log
session.json
~~~

pneumatic.ndjson 记录已发送命令、ESP 返回确认和气动状态；session.json 记录读取到的气动配置。它们用于追溯软件链路，并不能替代万用表、压力表或气路测试。

## 启动

唯一推荐入口：

~~~powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\start_host_app.cmd
~~~

启动器会同步运行时配置、检查 2.4 GHz 热点、启动异步模型服务、等待 HTTP 健康状态，再启动 UI。旧 run_host_app.cmd 不是当前链路入口。

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
