# AIX 脉盔上位机

这是 AIX 脉盔项目的 PC 端可视化程序，独立于 ESP-IDF 固件工程。它用于比赛调试和演示阶段，把下位机压力数据、PC 摄像头临时视觉特征、ESP 风险结果、气囊模拟动作和后续运动模块数据放在同一个界面中验证。

当前版本中，PC 摄像头只是未来真实摄像头模块的临时替身：PC 负责读取本机/网络摄像头并提取图像接近趋势特征，最终风险等级和气囊策略以 ESP32-S3 返回的 `risk` / `actuator` 事件为准。

## 顶层职责

```text
host_app
├─ 串口链路：读取 ESP32-S3 pressure / risk / actuator / motion，兼容旧 PRESSURE 日志
├─ 传感器总览：压力、速度、加速度、ESP 风险、气囊目标
├─ 压力面板：曲线、状态、动态缩放、自动跟随
├─ 运动模块：速度/加速度 UI 占位，等待真实模块接入
├─ 视觉闭环：摄像头画面、光流趋势特征、视觉发送状态、ESP 风险原因
├─ 事件流：记录串口、模拟、摄像头启动/停止/错误等关键事件
└─ CSV 记录：当前只记录压力样本，运行产物写入 logs/
```

设计边界：

- 上位机负责演示、调试和算法验证，不直接控制最终产品的安全执行动作。
- PC 摄像头输入暂时在上位机侧完成，用于快速验证 UI、算法趋势和串口数据流。
- 速度、加速度模块本阶段只预留显示和解析接口，不伪造输入，不参与风险融合。
- 压力监测默认由 ESP 固件开启，上位机不提供关闭压力监测的可见开关。

## 功能

- 读取 ESP32-S3 串口 NDJSON 气压数据。
- 实时显示传感器总览、原始气压、滤波气压、ADC 原始值、电压、有效性和过压状态。
- 兼容旧版 `PRESSURE,seq=...` 日志，便于从早期固件过渡。
- 气压曲线支持动态 Y 轴缩放，低压小波动也能看清楚。
- 气压曲线支持“自动跟随”按钮：开启时横轴跟随最新样本，关闭后可手动拖拽查看历史。
- 提供模拟数据模式，未连接开发板时也能检查界面。
- 可选记录 CSV，文件写入本地 `logs/`，该目录不会上传到 GitHub。
- 支持本机摄像头编号和手机 IP/RTSP/MJPEG 地址作为临时视觉输入。
- 使用 OpenCV 光流提取 `looming`、`area_rate`、`center_motion` 和 `confidence`。
- 通过双向串口向 ESP32-S3 发送 `vision` 事件，并解析 ESP 返回的 `risk` / `actuator` 事件。
- 预留 `motion` 事件解析与 UI 显示，后续接速度/加速度模块。

## 目录结构

```text
host_app/
├─ aix_host_app/        # 上位机源码
│  ├─ widgets/          # 界面模块：链路、总览、压力、运动、视觉、事件流
│  ├─ vision/           # 摄像头输入与光流趋势分析
│  ├─ app.py            # 主窗口和线程生命周期
│  ├─ serial_source.py  # 串口读取/写入线程
│  ├─ parsers.py        # 串口数据解析
│  ├─ models.py         # 压力/运动/风险/动作数据模型
│  └─ plot_scaling.py   # 曲线视窗缩放策略
├─ tests/               # 单元测试
├─ requirements.txt     # Python 依赖清单
├─ run_host_app.cmd     # Windows 一键启动脚本
└─ README.md
```

## 环境

统一只使用这一套虚拟环境：

```text
D:\Projects\IOTCompetition\ProjectFile\.venv
```

不要再创建 `host_app\.venv`。如果需要重新安装依赖，在 PowerShell 里执行：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
.\.venv\Scripts\Activate.ps1
cd .\host_app
python -m pip install -r requirements.txt
```

## 运行

推荐直接运行启动脚本，不需要手动激活虚拟环境，也不会误用 conda 的 `(base)`：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\run_host_app.cmd
```

也可以手动使用唯一虚拟环境运行：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m aix_host_app
```

## 使用方式

1. 选择 ESP32-S3 对应串口。
2. 波特率保持与固件监视器一致，默认可先用 `115200`。
3. 点击“连接”。
4. 若没有开发板，勾选“模拟数据”。
5. 需要记录时勾选“记录 CSV”。
6. 查看历史数据时关闭“自动跟随”，拖拽或缩放曲线；回到最新数据时重新开启。
7. 摄像头来源选择“本机摄像头”时填 `0`、`1` 等编号；选择“手机/IP 摄像头”时填 `http://手机IP:端口/video`、MJPEG 地址或 `rtsp://...`。
8. 点击“启动摄像头”后右侧显示实时画面；上位机会提取接近趋势特征并在串口连接时发送给 ESP32-S3，风险等级以 ESP 返回结果为准。

## 摄像头模块设计

第一版实现的公共接口：

- `CameraSourceConfig(kind, value, width=640, height=360, fps=15)`：描述输入来源。
- `kind="local"`：`value` 为本机摄像头编号，例如 `0`。
- `kind="url"`：`value` 为 HTTP/MJPEG/RTSP 地址。
- `CameraReader.frame_received`：向 UI 推送 `CameraFrame`。
- `CameraReader.error_changed`：输出中文错误，例如缺少 OpenCV、摄像头打不开、视频流中断。
- `VisionTrendAnalyzer`：当前使用 Farneback 光流估计扩张趋势、中心运动和前景面积变化。
- `VisionPanel.update_analysis(result)`：显示 PC 摄像头提取的本地视觉特征。
- `VisionPanel.update_esp_risk(event)` / `update_actuator(event)`：显示 ESP32-S3 返回的权威风险等级和气囊模拟动作。

切换到真实摄像头模块时优先复用这两条路径：

1. 如果真实模块能输出 MJPEG/RTSP/HTTP 视频流，直接填入 URL 输入框。
2. 如果真实模块通过 ESP32-S3 或其他链路输出视觉事件，则新增一个视觉事件源，保持 UI 面板和风险结果数据结构不变。

## 视觉触发闭环

当前阶段没有真实速度、加速度、IMU、雷达或摄像头模块。上位机用 PC 摄像头模拟未来视觉模块，使用光流扩张、中心运动和前景面积变化提取 `looming`、`area_rate`、`center_motion` 和 `confidence`。这些特征每 100 ms 最多发送一条到 ESP32-S3。

上位机发送：

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

ESP32-S3 返回：

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"actuator","version":1,"seq":35,"ts_ms":43100,"mode":"sim","target_pct":80,"pump":"hold","valve":"closed"}
```

## 运动模块预留

上位机布局已预留速度和加速度显示区域。本阶段不伪造速度/加速度输入，默认显示 `模块未接入`。后续模块接入时建议使用：

```json
{"type":"motion","version":1,"seq":1,"ts_ms":1000,"speed_mps":0.0,"accel_mps2":0.0,"speed_valid":false,"accel_valid":false}
```

该事件目前只用于显示，不参与 ESP 风险融合。

## 固件串口数据格式

固件默认启用压力监测，每 1000 ms 输出一行压力事件：

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `seq` | 固件侧样本序号 |
| `ts_ms` | 固件启动后的毫秒时间戳 |
| `raw` | ADC 原始值 |
| `mv` | ADC 校准后的电压毫伏值 |
| `kpa` | 由电压换算出的原始气压 |
| `filtered_kpa` | 指数滤波后的气压 |
| `over_pressure` | 是否超过软过压阈值 |
| `valid` | 传感器电压是否处于预期范围 |

## 测试

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m unittest discover -s tests
..\.venv\Scripts\python.exe -m compileall -q aix_host_app tests
```

测试覆盖：

- `pressure`、`risk`、`actuator`、`motion` NDJSON 解析。
- 旧版 `PRESSURE` 日志解析。
- 坏行和缺字段处理。
- 气压历史缓存、模拟数据生成、X/Y 轴动态缩放策略。
- 摄像头配置、视觉事件发送桥和光流趋势分析器。

## 后续扩展点

- 真实摄像头模块接入后，可新增图像源适配器，或在模块输出 MJPEG/RTSP/HTTP 流时直接复用 URL 输入。
- 速度、加速度模块接入后，可将 `motion` 显示从占位状态切换为有效状态。
- 雷达、IMU 和视觉结果最终应合成为统一风险等级，但安全关键动作仍由端侧规则控制。
- 云端大模型建议可以作为非安全关键事件进入事件流，不参与本地紧急防护闭环。
