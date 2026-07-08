# AIX 脉盔上位机

这是 AIX 脉盔项目的 PC 端可视化与调试程序，独立于 ESP-IDF 固件工程。它服务比赛开发阶段：把 ESP32-S3 的压力数据、风险结果、气囊模拟动作、摄像头视觉结果和后续语音/执行事件放在同一个界面中验证。

上位机不是最终产品的安全执行控制器。最终摄像头采集、轻量目标检测、距离估计、风险融合、过压保护和气囊执行都应尽量由 ESP32-S3 本地完成；上位机负责调试、演示、数据记录和算法过渡。

## 7.8 架构中的职责

```text
host_app
├─ 当前已实现
│  ├─ 串口链路：读取 ESP32-S3 pressure / risk / actuator
│  ├─ 压力面板：显示原始气压、滤波气压、电压、有效性和过压状态
│  ├─ 视觉面板：用 PC/手机摄像头生成临时 vision 事件
│  ├─ 风险展示：显示 ESP32-S3 返回的 risk 和 actuator
│  ├─ 事件流：记录串口、模拟、摄像头、风险和错误事件
│  └─ CSV 记录：保存调试数据
│
└─ 下一阶段规划
   ├─ 展示 vision_detect：目标类别、bbox、confidence、distance_m、approaching
   ├─ 展示 risk v2：nearest_class、nearest_distance_m、ttc_s、category
   ├─ 展示 voice：语音播报文本和播放状态
   ├─ 支持单目端侧检测调试：OV5640/OV2640 输出结果可视化
   └─ 作为比赛演示台：把视觉、压力、风险、气囊目标串成闭环
```

当前 PC/手机摄像头通路是临时验证工具，不是最终安全闭环。7.8 主线是 `OV5640 单目摄像头 -> ESP32-S3 轻量检测 -> 单目粗测距 -> risk_fusion -> 语音/气囊执行`。

## 当前功能

- 读取 ESP32-S3 串口 NDJSON 气压数据。
- 实时显示传感器总览、原始气压、滤波气压、ADC 原始值、电压、有效性和过压状态。
- 兼容旧版 `PRESSURE,seq=...` 日志，便于从早期固件过渡。
- 气压曲线支持动态 Y 轴缩放，低压小波动也能看清。
- 气压曲线支持“自动跟随”：开启时横轴跟随最新样本，关闭后可手动拖拽查看历史。
- 支持模拟数据模式，未连接开发板时也能检查界面。
- 可选记录 CSV，文件写入本地 `logs/`，该目录不会上传到 GitHub。
- 支持本机摄像头编号和手机 IP/RTSP/MJPEG 地址作为临时视觉输入。
- 使用 OpenCV 光流提取 `looming`、`area_rate`、`center_motion` 和 `confidence`。
- 通过双向串口向 ESP32-S3 发送临时 `vision` 事件，并解析 ESP 返回的 `risk` / `actuator` 事件。
- 已预留 `motion` 事件解析与 UI 显示，后续可以作为 IMU 或运动状态扩展入口。

## 目录结构

```text
host_app/
├─ aix_host_app/
│  ├─ widgets/
│  │  ├─ connection_panel.py        # 串口、模拟数据、记录开关
│  │  ├─ sensor_overview_panel.py   # 传感器总览
│  │  ├─ pressure_panel.py          # 压力曲线和状态
│  │  ├─ motion_panel.py            # 运动/IMU 显示占位
│  │  ├─ vision_panel.py            # 摄像头画面、视觉特征、ESP 风险
│  │  └─ event_timeline.py          # 事件流
│  ├─ vision/
│  │  ├─ camera.py                  # 摄像头来源配置
│  │  ├─ reader.py                  # 摄像头读取线程
│  │  ├─ analysis.py                # 当前 PC 光流趋势分析
│  │  └─ bridge.py                  # vision 事件发送桥
│  ├─ app.py                        # 主窗口和线程生命周期
│  ├─ serial_source.py              # 串口读取/写入线程
│  ├─ parsers.py                    # 串口数据解析
│  ├─ models.py                     # 数据模型
│  ├─ history.py                    # 历史缓存
│  ├─ simulation.py                 # 模拟数据
│  └─ plot_scaling.py               # 曲线缩放策略
├─ tests/
├─ requirements.txt
├─ run_host_app.cmd
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
2. 波特率保持与固件一致，当前可先用 `115200`。
3. 点击“连接”。
4. 如果没有开发板，勾选“模拟数据”检查界面状态。
5. 需要记录时勾选“记录 CSV”。
6. 查看历史数据时关闭“自动跟随”，拖拽或缩放曲线；回到最新数据时重新开启。
7. 摄像头来源选择“本机摄像头”时填 `0`、`1` 等编号；选择“手机/IP 摄像头”时填 HTTP/MJPEG/RTSP 地址。
8. 点击“启动摄像头”后，右侧显示实时画面；上位机会提取接近趋势特征，并在串口连接时发送给 ESP32-S3。
9. 风险等级和气囊动作以 ESP32-S3 返回的 `risk` / `actuator` 为准。

## 摄像头输入设计

第一版已经实现可替换输入接口，方便从 PC 摄像头过渡到真实摄像头模块：

- `CameraSourceConfig(kind, value, width=640, height=360, fps=15)`：描述输入来源。
- `kind="local"`：`value` 为本机摄像头编号，例如 `0`。
- `kind="url"`：`value` 为 HTTP/MJPEG/RTSP 地址。
- `CameraReader.frame_received`：向 UI 推送 `CameraFrame`。
- `CameraReader.error_changed`：输出中文错误，例如缺少 OpenCV、摄像头打不开、视频流中断。
- `VisionTrendAnalyzer`：当前使用 Farneback 光流估计扩张趋势、中心运动和前景面积变化。
- `VisionPanel.update_analysis(result)`：显示 PC 摄像头提取的临时视觉特征。
- `VisionPanel.update_esp_risk(event)` / `update_actuator(event)`：显示 ESP32-S3 返回的权威风险等级和气囊模拟动作。

7.8 后续不再把 PC 光流当成最终方案。真实产品方向是：ESP32-S3 侧接入 OV5640/OV2640，输出 `vision_detect`，上位机只负责显示和记录。

## 当前串口协议

### pressure

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

### 临时 vision

上位机发送给 ESP32-S3：

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

### risk / actuator

ESP32-S3 返回：

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"actuator","version":1,"seq":35,"ts_ms":43100,"mode":"sim","target_pct":80,"pump":"hold","valve":"closed"}
```

## 下一阶段协议

### vision_detect

ESP32-S3 端侧视觉检测结果。上位机需要展示目标框、类别、置信度、距离和接近趋势。

```json
{
  "type": "vision_detect",
  "version": 1,
  "seq": 42,
  "ts_ms": 50000,
  "source": "ov5640",
  "objects": [
    {
      "class": "truck",
      "confidence": 0.82,
      "bbox": [78, 42, 65, 48],
      "distance_m": 5.2,
      "approaching": true
    }
  ],
  "nearest_distance_m": 5.2,
  "ttc_s": 4.1,
  "valid": true
}
```

### risk v2

```json
{"type":"risk","version":2,"seq":43,"ts_ms":50020,"level":40,"target_pct":40,"reason":"truck_approaching","category":"vision_warning","nearest_class":"truck","nearest_distance_m":5.2,"ttc_s":4.1,"pressure_safe":true,"pressure_state":"safe"}
```

新增字段在界面上的建议呈现：

| 字段 | 用途 |
| --- | --- |
| `category` | 区分视觉提醒、紧急保护、安全停止等类型 |
| `nearest_class` | 当前最近或最高风险目标类别 |
| `nearest_distance_m` | 单目粗测距结果 |
| `ttc_s` | 估算碰撞时间，允许为空或无效 |
| `pressure_safe` / `pressure_state` | 判断能否继续升高目标充气比例 |

### voice

```json
{"type":"voice","version":1,"seq":43,"ts_ms":50030,"text":"前方大货车接近，请减速","played":true}
```

## 规划目标

1. 在 `models.py` 增加 `VisionDetectEvent`、`VisionObject`、`VoiceEvent`，并扩展 `RiskEvent` v2 字段。
2. 在 `parsers.py` 解析 `vision_detect`、`risk v2`、`voice`，保持对当前 v1 协议兼容。
3. 在 `vision_panel.py` 显示目标类别、bbox、距离、接近趋势和置信度。
4. 在 `sensor_overview_panel.py` 显示最近目标、TTC、风险类别和目标充气比例。
5. 在 `event_timeline.py` 记录视觉检测、语音播报、气囊动作和关键告警。
6. CSV 记录从压力样本扩展为可选多源事件记录。

## 测试

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m unittest discover -s tests
..\.venv\Scripts\python.exe -m compileall -q aix_host_app tests
```

测试当前覆盖：

- `pressure`、`risk`、`actuator`、`motion` NDJSON 解析。
- 旧版 `PRESSURE` 日志解析。
- 坏行和缺字段处理。
- 气压历史缓存、模拟数据生成、X/Y 轴动态缩放策略。
- 摄像头配置、视觉事件发送桥和光流趋势分析器。

后续接入 `vision_detect`、`risk v2`、`voice` 时，需要同步补充解析器、数据模型、面板更新和单元测试。

## 安全边界

- 上位机可以生成临时 `vision` 事件，但最终产品的视觉判断和执行决策应在 ESP32-S3 本地完成。
- 上位机展示的是调试和演示结果，不直接控制真实泵阀。
- 真实气囊硬件接入前，界面上的 `target_pct` 和 `actuator` 都应视为模拟输出。
- 摄像头检测、单目距离估计和 PC 演示结果都不能替代本地过压保护和失效安全策略。
