# AIX 脉盔

这是面向骑行场景的 ESP32-S3 安全头盔原型。当前工程包含真实压力采集、OV5640 健康采帧，以及由 PC RTX GPU 执行的 Depth Anything 3 相对深度推理。

## 当前链路

```text
XGZP6847A -> ESP32-S3 pressure_sensor -> pressure NDJSON -> PC 上位机
OV5640 -> ESP32-S3 camera_local -> Wi-Fi latest JPEG preview -> PC 上位机
```

JPEG 通过 ESP32-S3 的 Wi-Fi 链路提供给本机上位机；串口只传 `camera_status`、`camera_preview` 等状态，不传图像字节。`vision_depth` 仍保留为可选的相对深度协议，不是米制距离、碰撞结论或执行器指令。

## 目录

```text
ProjectFile/
├─ AIX/       # ESP-IDF 固件：压力采集、OV5640 采帧
├─ host_app/  # PySide6 状态、压力曲线、CSV 与 motion 占位
├─ docs/      # 接线与项目审阅文档
└─ scripts/   # 统一验证脚本
```

## 已实现与未实现

| 项目 | 状态 |
| --- | --- |
| XGZP6847A 压力采集 | 已实现 |
| OV5640 QVGA/JPEG 健康采帧与恢复 | 已实现，待实机五分钟验收 |
| 上位机 OV5640 连接状态、详情与 Wi-Fi 画面预览 | 已实现，待热点实机验收 |
| PC 端 DA3-SMALL 相对深度服务 | 已实现，待 OV5640 Wi-Fi 实机闭环验收 |
| ESP32-S3 端视觉模型 | 不采用；ESP32-S3 负责采帧、上传和结果上报 |
| JPEG Wi-Fi 上送 | 已实现，待实机网络验收 |
| 风险融合、语音、气囊执行链路 | 已删除，等待真实模型与安全方案确定后重建 |

## 串口协议

支持 `pressure`、`camera_status`、`camera_preview`，并保留上位机 `motion` 占位协议。压力事件的 `valid:false` 表示电压异常（可能未接入），上位机只显示 raw/mV 诊断值，不显示或记录 kPa。

```json
{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg","frame_bytes":18432,"fps":5.0,"frames_ok":12,"capture_failures":0,"psram":false,"valid":true}
```

上位机在串口连接后 3 秒内收到 `valid:true` 显示“OV5640：状态正常”；收到无效状态或超时显示“连接异常”。点击状态文字可展开参数详情。

## OV5640 Wi-Fi 画面预览

1. 在 Windows 移动热点的“属性”中将频段选为 **2.4 GHz**，保持热点开启。
2. 本机私有配置 `AIX/sdkconfig.preview` 保存热点名称和密码；该文件已被 Git 忽略，不能提交。
3. 编译并烧录后，ESP32-S3 取得 IP 会通过串口发送 `camera_preview` 事件，上位机自动轮询 `http://<ESP-IP>:8080/capture.jpg` 并显示画面。

若上位机显示“画面预览不可用：ssid_empty”，说明本机私有配置缺少热点参数；若持续读取失败，优先确认热点不是 5 GHz 且电脑和 ESP32-S3 在同一热点。

## 构建与验证

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BuildFirmware
```

固件默认启用 OV5640 和 Wi-Fi 画面预览；如需无相机调试，可在 `menuconfig` 关闭 `AIX_ENABLE_LOCAL_CAMERA`。如需启用原有 DA3 Wi-Fi 上传，先关闭 `AIX_ENABLE_CAMERA_PREVIEW`，两项不能同时启用。

## DA3 本地模型

所有模型资产固定在 [`Models/DepthAnything3`](Models/DepthAnything3)：官方源码、独立 CUDA 环境、本地权重、缓存、服务和日志均不写入项目外部目录。启动 PC 服务：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\Models\DepthAnything3
.\run_service.ps1
```

在 ESP-IDF `menuconfig` 启用 `AIX_ENABLE_VISION_UPLINK`，设置 Wi-Fi SSID、密码和 PC 服务 URL 后，ESP32-S3 每秒上传一张最新 JPEG。

## PC 本地识别与风险记录

当前默认链路由上位机从 `camera_preview` 拉取最新 JPEG：预览约 2.5 FPS，PC 每秒取一张最新帧交给 DA3-SMALL 和 TorchVision SSDLite。上位机显示 `0–100` 相对视觉风险、检测框和模型耗时，并将精简风险通过 ESP 的 `POST /risk` 接口同步；该风险暂不驱动气囊、蜂鸣器或其他执行器。

串口连接成功后自动创建 `F:\OV5640\YYYYMMDD_HHMMSS` 会话目录。目录包含原始 JPEG、`vision.ndjson`、`telemetry.ndjson`、`pressure.csv` 和 `session.json`。数据根目录可在上位机左侧选择，首次默认 `F:\OV5640`。

第一版风险是“前方近物占比 + 相关目标检测 + 连续帧接近趋势”的相对指标，不是米制距离或碰撞概率。后续升级建议：相机内参标定与 DA3Metric、TTC/目标跟踪、骑行场景数据集微调、更加精确的检测器，以及基于会话回放的参数标定。

## 安全边界

- 当前是采集与状态监测原型，不是自动避撞或气囊控制系统。
- 正常 FPS 不能视为目标识别、距离估算或碰撞判断已经完成。
- 实机接线、连续采帧和故障恢复验收完成前，不得将 OV5640 标记为已完成硬件验证。
