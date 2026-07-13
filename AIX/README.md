# AIX ESP32-S3 固件工程

固件负责压力采集、OV5640 健康采帧，以及可选的 Wi-Fi JPEG 上传。Depth Anything 3 在 PC RTX GPU 上运行；固件只接收紧凑 JSON 结果并输出 `vision_depth`。

## 启动链路

```text
app_main
├─ pressure_sensor_start_task()
│  └─ 每秒输出 pressure NDJSON
└─ camera_local_start_task()           # CONFIG_AIX_ENABLE_LOCAL_CAMERA=y
   └─ QVGA/JPEG 采帧、失败恢复、每秒输出 camera_status
      └─ vision_uplink（可选）-> PC /v1/infer -> vision_depth
```

`CONFIG_AIX_ENABLE_LOCAL_CAMERA` 默认开启，可在 ESP-IDF `menuconfig` 中关闭。采帧周期由 `CONFIG_AIX_CAMERA_CAPTURE_PERIOD_MS` 配置；状态上报固定为 1000 ms。

## 模块

```text
AIX/main/
├─ main.c                         # 任务装配
├─ pressure_sensor.c/h            # ADC1_CH0 / GPIO1 压力采集
├─ camera_local.c/h               # OV5640 QVGA JPEG 健康采帧
├─ camera_board_devkitc1_ov5640.h # DevKitC-1 固定 DVP 接线
├─ vision_uplink.c/h               # Wi-Fi HTTP 上传与模型响应校验
└─ idf_component.yml              # esp32-camera 依赖
```

## camera_status

`camera_status` 不包含 JPEG 字节；JPEG 仅由 `vision_uplink` 通过 Wi-Fi HTTP 请求体发送给 PC。返回的 `vision_depth` 只包含相对深度统计、置信度和延迟，不驱动风险或执行器逻辑。

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
- 未实现：米制距离、距离/TTC、JPEG 串口传输、语音、气泵、电磁阀、气囊控制。
- 实机验收：先配置 Wi-Fi 和 PC 服务 URL，验证五分钟连续采帧、HTTP 回传、断网恢复和 `vision_depth` 串口上报。
