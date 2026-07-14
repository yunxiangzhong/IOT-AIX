# AIX 脉盔上位机

这是 ESP32-S3 的调试与状态监测上位机。它显示压力数据、OV5640 健康状态与 Wi-Fi JPEG 画面、PC DA3 相对深度结果、事件流、CSV 记录，并保留 motion 预留面板。

上位机不使用本机摄像头、手机/IP 摄像头或 OpenCV 光流分析。它只根据 ESP32-S3 通过串口发布的 `camera_preview` 地址读取最新 OV5640 JPEG；图像字节不经过串口。

## 当前职责

```text
串口读取 pressure / camera_status / camera_preview / vision_depth / motion
├─ pressure：压力曲线、状态与 CSV
├─ camera_status：OV5640 折叠状态卡和参数详情
├─ camera_preview：ESP32-S3 Wi-Fi JPEG 地址，右侧视觉卡自动以约 2.5 FPS 更新
├─ vision_depth：DA3-SMALL 相对深度、置信度与推理延迟
└─ motion：保留未来模块接口
```

视觉区域包含最新 JPEG 预览和可点击的相机状态文字：

- `OV5640：等待状态`：未连接串口。
- `OV5640：状态正常`：3 秒内收到有效 `camera_status`。
- `OV5640：连接异常`：收到 `valid:false` 或连续 3 秒未收到状态。

点击状态文字可就地展开分辨率、格式、FPS、帧大小、成功帧、失败次数、PSRAM 和最后更新时间。

PC 视觉流水线会在预览之外每秒选取一张最新 JPEG，调用本地 DA3-SMALL + TorchVision SSDLite，生成 `0–100` 相对视觉风险。右侧默认显示检测框，可切换原图；顶部同步显示风险等级、主导目标、推理耗时和 ESP 风险确认状态。风险通过 ESP 的 `POST /risk` 接收，但当前不参与执行器控制。

串口连接成功后自动记录到 `F:\OV5640\YYYYMMDD_HHMMSS`。可以在左侧选择数据根目录；每个会话保存 `frames/`、`vision.ndjson`、`telemetry.ndjson`、`pressure.csv` 和 `session.json`。

压力事件 `valid:false` 时，上位机显示 `— kPa` 和 raw/mV 诊断值；该样本不会画入曲线或写入 CSV，避免未接传感器时将残留滤波值误判为压力。

## 目录

```text
host_app/
├─ aix_host_app/
│  ├─ app.py             # 主窗口、串口路由、记录
│  ├─ models.py          # pressure / camera_status / camera_preview / motion
│  ├─ parsers.py         # 支持协议解析
│  └─ widgets/           # 压力、motion、OV5640 状态、事件流
├─ tests/
├─ requirements.txt
└─ run_host_app.cmd
```

## 运行

直接双击 `start_host_app.cmd` 即可启动上位机；脚本会先检查项目 Python 环境和本地视觉模型环境，随后把 `AIX/sdkconfig.preview` 同步到活动固件配置、自动启动 Windows 移动热点并确认 SSID 一致，最后启动上位机。缺失或失败时会保留窗口并显示具体原因。

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\start_host_app.cmd
```

项目统一使用 `D:\Projects\IOTCompetition\ProjectFile\.venv`。

Windows 热点必须设为 **2.4 GHz**。先运行 `./AIX/configure_preview.ps1` 写入热点配置，再重新编译并烧录固件；保持串口连接即可自动收到预览地址并显示画面。若事件流出现 `ssid_empty` 或 `wifi_disconnected_<reason>`，按事件原因检查本机热点配置。

热点自动启动只影响 PC。ESP32-S3 的 SSID 和密码属于编译期配置，因此首次配置或修改热点密码后仍需重新编译并烧录一次；此后 ESP 固件会在启动和断线时自动执行 `esp_wifi_connect()`。

## 验证

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 边界

- `camera_status` 表示相机健康；`vision_depth` 表示 PC 模型成功返回相对深度，二者缺一不可。
- `vision_depth` 不是米制距离，不直接控制风险或气囊。
- 当前风险和气囊卡片只是未来 UI 占位，不接收旧 risk/actuator 协议。
- `motion` 协议与面板保留，但当前固件没有运动数据源。
- 第一版风险是相对视觉风险，不是碰撞概率；后续可加入相机标定、米制深度、TTC/跟踪和骑行数据集微调。
