# AIX 脉盔

这是面向骑行场景的 ESP32-S3 安全头盔原型。当前工程已收敛为真实压力采集和 ESP32-S3 外接 OV5640 健康采帧；视觉模型后续直接部署在 ESP32-S3。

## 当前链路

```text
XGZP6847A -> ESP32-S3 pressure_sensor -> pressure NDJSON -> PC 上位机
OV5640 -> ESP32-S3 camera_local -> camera_status NDJSON -> PC 上位机状态卡
```

上位机不再连接本机、手机或 IP 摄像头，不接收 JPEG，也不做光流判断。`camera_status` 只证明相机初始化和采帧健康，不代表目标检测已完成。

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
| ESP32-S3 端视觉模型 | 未实现 |
| JPEG 上送、PC/手机摄像头、光流判断 | 已删除 |
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

## 安全边界

- 当前是采集与状态监测原型，不是自动避撞或气囊控制系统。
- 正常 FPS 不能视为目标识别、距离估算或碰撞判断已经完成。
- 实机接线、连续采帧和故障恢复验收完成前，不得将 OV5640 标记为已完成硬件验证。
