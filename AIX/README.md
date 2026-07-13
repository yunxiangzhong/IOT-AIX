# AIX ESP32-S3 固件工程

固件仅负责两项运行任务：XGZP6847A 压力采集与 OV5640 本地健康采帧。视觉模型会在后续直接部署于 ESP32-S3；当前不包含 PC 摄像头、光流、模拟目标、风险融合、语音或气囊执行模块。

## 启动链路

```text
app_main
├─ pressure_sensor_start_task()
│  └─ 每秒输出 pressure NDJSON
└─ camera_local_start_task()           # CONFIG_AIX_ENABLE_LOCAL_CAMERA=y
   └─ QVGA/JPEG 采帧、失败恢复、每秒输出 camera_status
```

`CONFIG_AIX_ENABLE_LOCAL_CAMERA` 默认开启，可在 ESP-IDF `menuconfig` 中关闭。采帧周期由 `CONFIG_AIX_CAMERA_CAPTURE_PERIOD_MS` 配置；状态上报固定为 1000 ms。

## 模块

```text
AIX/main/
├─ main.c                         # 任务装配
├─ pressure_sensor.c/h            # ADC1_CH0 / GPIO1 压力采集
├─ camera_local.c/h               # OV5640 QVGA JPEG 健康采帧
├─ camera_board_devkitc1_ov5640.h # DevKitC-1 固定 DVP 接线
└─ idf_component.yml              # esp32-camera 依赖
```

## camera_status

`camera_status` 不包含 JPEG 字节，不触发模型、不驱动任何风险或执行器逻辑。它仅表示本地相机是否初始化成功、当前帧是否有效及采帧统计。

```json
{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg","frame_bytes":18432,"fps":5.00,"frames_ok":12,"capture_failures":0,"psram":false,"valid":true}
```

## 构建

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
idf.py set-target esp32s3
idf.py build
idf.py flash monitor
```

接线与实机验收见 [`../docs/hardware/ov5640-devkitc1-wiring.md`](../docs/hardware/ov5640-devkitc1-wiring.md)。

## 当前边界

- 已实现：压力采集、OV5640 JPEG 健康采帧、状态上报与失败重试。
- 未实现：目标检测、距离/TTC、JPEG 串口传输、语音、气泵、电磁阀、气囊控制。
- 下一步：先完成 OV5640 实机五分钟稳定采帧和断线恢复验收，再在 ESP32-S3 端接入视觉模型。
