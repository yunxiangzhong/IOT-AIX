# AIX 脉盔

这是面向骑行场景的 ESP32-S3 安全头盔原型。当前工程包含真实压力采集、OV5640 健康采帧，以及由 PC RTX GPU 执行的 Depth Anything 3 相对深度推理。

## 当前链路

```text
XGZP6847A -> ESP32-S3 pressure_sensor -> pressure NDJSON -> PC 上位机
OV5640 -> ESP32-S3 camera_local -> Wi-Fi HTTP JPEG -> PC DA3-SMALL -> HTTP JSON -> ESP32-S3 vision_depth NDJSON -> PC 上位机
```

JPEG 只通过 ESP32-S3 的 Wi-Fi 链路上传给本机推理服务；串口上位机不接收图像字节，只显示 `camera_status` 与 `vision_depth`。`vision_depth` 是相对深度统计，不是米制距离、碰撞结论或执行器指令。

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
| 上位机 OV5640 连接状态与详情 | 已实现 |
| PC 端 DA3-SMALL 相对深度服务 | 已实现，待 OV5640 Wi-Fi 实机闭环验收 |
| ESP32-S3 端视觉模型 | 不采用；ESP32-S3 负责采帧、上传和结果上报 |
| JPEG Wi-Fi 上送 | 已实现，待实机网络验收 |
| 风险融合、语音、气囊执行链路 | 已删除，等待真实模型与安全方案确定后重建 |

## 串口协议

支持 `pressure`、`camera_status`，并保留上位机 `motion` 占位协议。

```json
{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg","frame_bytes":18432,"fps":5.0,"frames_ok":12,"capture_failures":0,"psram":false,"valid":true}
```

上位机在串口连接后 3 秒内收到 `valid:true` 显示“OV5640：状态正常”；收到无效状态或超时显示“连接异常”。点击状态文字可展开参数详情。

## 构建与验证

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BuildFirmware
```

固件默认启用 OV5640；如需无相机调试，可在 `menuconfig` 关闭 `AIX_ENABLE_LOCAL_CAMERA`。

## DA3 本地模型

所有模型资产固定在 [`Models/DepthAnything3`](Models/DepthAnything3)：官方源码、独立 CUDA 环境、本地权重、缓存、服务和日志均不写入项目外部目录。启动 PC 服务：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\Models\DepthAnything3
.\run_service.ps1
```

在 ESP-IDF `menuconfig` 启用 `AIX_ENABLE_VISION_UPLINK`，设置 Wi-Fi SSID、密码和 PC 服务 URL 后，ESP32-S3 每秒上传一张最新 JPEG。

## 安全边界

- 当前是采集与状态监测原型，不是自动避撞或气囊控制系统。
- 正常 FPS 不能视为目标识别、距离估算或碰撞判断已经完成。
- 实机接线、连续采帧和故障恢复验收完成前，不得将 OV5640 标记为已完成硬件验证。
