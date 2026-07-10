# OV5640 直连 ESP32-S3-DevKitC-1（P1）

本页对应 18 针、3.3 V、DVP 并口 OV5640 排针板。P1 只验证 QVGA JPEG 稳定采帧和 `camera_status`；不传 JPEG，不做自动对焦、补光、YOLO、测距或真实执行控制。

## 固定接线

| OV5640 | ESP32-S3-DevKitC-1 | 用途 |
| --- | --- | --- |
| 3.3V | 3V3 | 仅接 3.3 V，禁止接 5 V |
| GND | GND | 必须共地 |
| SDA | GPIO4 | SCCB 数据 |
| SCL | GPIO5 | SCCB 时钟 |
| XCLK | GPIO6 | 20 MHz 相机时钟 |
| PCLK | GPIO7 | 像素时钟 |
| VSYNC | GPIO8 | 帧同步 |
| HREF | GPIO9 | 行同步 |
| D0–D7 | GPIO10–GPIO17 | DVP 数据，按顺序一一连接 |
| PWDN | GPIO18 | 电源休眠控制 |
| RST | GPIO21 | 硬件复位 |

不要把 GPIO0、GPIO19/20、GPIO35/36/37、GPIO38、GPIO43/44 分配给本摄像头：它们分别涉及启动、USB、板载存储/PSRAM、RGB 或串口等板级功能。

## 运行配置

`sdkconfig.camera.defaults` 会关闭模拟 `vision_detect`，开启本地相机。固定参数：`320×240`、JPEG、20 MHz XCLK、质量 12、DRAM 单缓冲、200 ms 采帧周期（目标 5 FPS）。当前配置不依赖 PSRAM；未经确认前不要开启双缓冲。

在原生 ESP-IDF PowerShell 中构建：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -IdfProfile camera
```

烧录后，串口应每秒出现一条类似状态；它只包含健康信息，不含图像字节：

```json
{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg","frame_bytes":18432,"fps":5.00,"frames_ok":12,"capture_failures":0,"psram":false,"valid":true}
```

## 故障判定

- `valid:false`：初始化失败、空帧、非 JPEG 帧或 JPEG 首尾标记错误。
- 连续 3 次采帧失败：驱动会 `deinit/reinit`，不会重启 ESP32-S3。
- 初始化失败或重启后失败：每 2 秒重试一次。
- 相机异常不生成 `vision_detect`，风险融合仍只使用 PC `vision` v1；若没有有效 PC 视觉，气囊目标保持 `0%`。

验收时连续运行至少 5 分钟并检查不少于 100 帧、JPEG 有效、无系统重启和采帧失败率低于 1%。若模组标有 R2/R8，请先确认其 PSRAM 配置后再单独设计双缓冲 profile。
