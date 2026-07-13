# OV5640 直连 ESP32-S3-DevKitC-1（P1）

本页对应图示的正点原子 18 针、3.3 V、DVP 并口 OV5640 排针板。该模块自带 24 MHz 有源晶振，排针没有 XCLK，因此 ESP32-S3 不输出外部 XCLK。P1 只验证 QVGA JPEG 稳定采帧和 `camera_status`；不传 JPEG，不做自动对焦、补光、YOLO、测距或真实执行控制。

## 固定接线

| OV5640 | ESP32-S3-DevKitC-1 | 用途 |
| --- | --- | --- |
| 3.3V | 3V3 | 仅接 3.3 V，禁止接 5 V |
| GND | GND | 必须共地 |
| SDA | GPIO4 | SCCB 数据 |
| SCL | GPIO5 | SCCB 时钟 |
| XCLK | 不接 | 模块自带 24 MHz 有源晶振；GPIO6 悬空 |
| PCLK | GPIO7 | 像素时钟 |
| VSYNC | GPIO8 | 帧同步 |
| HREF | GPIO9 | 行同步 |
| D0–D7 | GPIO10–GPIO17 | DVP 数据，按顺序一一连接 |
| PWDN | GPIO18 | 电源休眠控制 |
| RST | GPIO21 | 硬件复位 |
| FLASH | 不接 | P1 不使用补光灯控制 |

不要把 GPIO0、GPIO19/20、GPIO35/36/37、GPIO38、GPIO43/44 分配给本摄像头：它们分别涉及启动、USB、板载存储/PSRAM、RGB 或串口等板级功能。

## 运行配置

固件默认开启本地相机；如需无相机调试，可在 ESP-IDF `menuconfig` 关闭 `AIX_ENABLE_LOCAL_CAMERA`。固定参数：`320×240`、JPEG、模块内部 24 MHz XCLK、质量 12、DRAM 单缓冲、200 ms 采帧周期（目标 5 FPS）。驱动使用 `pin_xclk = -1`，同时以 `24 MHz` 作为 OV5640 PLL/PCLK 配置依据。当前配置不依赖 PSRAM；未经确认前不要开启双缓冲。

在原生 ESP-IDF PowerShell 中构建：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BuildFirmware
```

烧录后，串口应每秒出现一条类似状态；它只包含健康信息，不含图像字节：

```json
{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg","frame_bytes":18432,"fps":5.00,"frames_ok":12,"capture_failures":0,"psram":false,"valid":true}
```

## 故障判定

- `valid:false`：初始化失败、空帧、非 JPEG 帧或 JPEG 首尾标记错误。
- 连续 3 次采帧失败：驱动会 `deinit/reinit`，不会重启 ESP32-S3。
- 初始化失败或重启后失败：每 2 秒重试一次。
- 相机异常只会发出无效 `camera_status`，上位机应显示“OV5640：连接异常”。当前不产生检测、风险或执行事件。

验收时连续运行至少 5 分钟并检查不少于 100 帧、JPEG 有效、无系统重启和采帧失败率低于 1%。若模组标有 R2/R8，请先确认其 PSRAM 配置后再单独设计双缓冲 profile。
