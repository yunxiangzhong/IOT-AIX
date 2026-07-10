# AIX 脉盔上位机

这是 AIX 脉盔项目的 PC 端可视化与调试程序。它用于开发和比赛演示阶段，把 ESP32-S3 的压力、风险、模拟视觉检测、OV5640 状态、语音事件和气囊模拟动作放在同一个界面里观察。

上位机不是最终产品的安全执行控制器。当前代码既支持 PC/手机摄像头光流输入，也能显示 ESP32-S3 模拟 `vision_detect` 事件；但真实视觉判断、过压保护和执行策略最终仍应落在 ESP32-S3 本地。

固件现在只会采用新鲜的 `vision_detect` v2；达到 500 ms 的 v2 snapshot 会回退到 `vision` v1，两个视觉输入都不可用时显示 0% 气囊目标。

项目级审阅和结构优化建议见 [`../docs/项目审阅与优化建议.md`](../docs/项目审阅与优化建议.md)。

## 当前真实职责

```text
host_app
├─ 串口双向通信
│  ├─ 读取 pressure / risk / actuator / vision_detect / voice
│  └─ 向 ESP32-S3 发送 PC 光流 vision v1
├─ 压力显示
│  ├─ 原始气压、滤波气压、电压、有效性、过压
│  └─ 动态 Y 轴和自动跟随
├─ 临时视觉输入
│  ├─ 本机摄像头
│  ├─ 手机/IP 摄像头
│  └─ OpenCV 光流趋势分析
├─ 视觉检测显示
│  └─ 显示 ESP 返回的 vision_detect 对象、距离、bbox、TTC
├─ OV5640 健康状态显示
│  └─ 显示 camera_status 的传感器、分辨率、FPS、帧长度、失败次数和 PSRAM 状态
├─ 风险和动作显示
│  ├─ risk v1 / risk v2
│  └─ actuator 模拟动作
├─ 事件流
│  ├─ 原始串口事件
│  ├─ voice 事件摘要
│  └─ 错误和状态
└─ CSV 记录
   └─ 当前主要记录压力样本
```

当前 `app.py` 已同时承担 UI 装配、串口和摄像头生命周期、事件路由、模拟数据及 CSV 记录。下一阶段建议逐步拆为 `SerialController`、`CameraController` 和 `EventRecorder`，让 widget 只负责显示与用户输入。

## 没有完成的内容

- 不直接控制真实气泵、电磁阀或泄气阀。
- 不播放真实语音，只显示和记录固件发来的 `voice` 事件。
- 不执行真实目标检测；PC 摄像头只做光流趋势分析。
- 不记录完整多源事件 CSV；当前 CSV 重点是压力样本。
- `motion` 面板是预留/占位，固件当前没有 IMU 或速度数据源。

## 目录结构

```text
host_app/
├─ aix_host_app/
│  ├─ widgets/
│  │  ├─ connection_panel.py        # 串口、模拟数据、记录开关
│  │  ├─ sensor_overview_panel.py   # 压力、风险、气囊目标总览
│  │  ├─ pressure_panel.py          # 压力曲线和状态
│  │  ├─ motion_panel.py            # 运动/IMU 显示占位
│  │  ├─ vision_panel.py            # 摄像头画面、光流特征、vision_detect、ESP 风险
│  │  └─ event_timeline.py          # 事件流
│  ├─ vision/
│  │  ├─ camera.py                  # 摄像头来源配置
│  │  ├─ reader.py                  # 摄像头读取线程
│  │  ├─ analysis.py                # Farneback 光流趋势分析
│  │  └─ bridge.py                  # vision v1 事件发送桥
│  ├─ app.py                        # 主窗口和事件路由
│  ├─ serial_source.py              # 串口读取/写入线程
│  ├─ parsers.py                    # pressure/risk/actuator/motion/vision_detect/camera_status/voice 解析
│  ├─ models.py                     # 数据模型
│  ├─ history.py                    # 历史缓存
│  ├─ simulation.py                 # 上位机压力模拟数据
│  └─ plot_scaling.py               # 曲线缩放策略
├─ tests/                           # 本机测试较完整，但当前被仓库规则整体忽略
├─ requirements.txt
├─ run_host_app.cmd
└─ README.md
```

## 环境

项目约定只使用这一套虚拟环境：

```text
D:\Projects\IOTCompetition\ProjectFile\.venv
```

不要再创建 `host_app\.venv`。安装依赖：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
.\.venv\Scripts\Activate.ps1
cd .\host_app
python -m pip install -r requirements.txt
```

依赖包括 PySide6、pyserial、pyqtgraph、numpy 和 opencv-python-headless。

## 运行

推荐使用启动脚本：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\run_host_app.cmd
```

也可以直接使用项目虚拟环境：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m aix_host_app
```

## 使用方式

1. 选择 ESP32-S3 对应串口。
2. 波特率保持与固件一致，当前可先用 `115200`。
3. 点击“连接”。
4. 如果没有开发板，勾选“模拟数据”只能检查上位机压力界面，不会产生固件 risk/voice/actuator 链路。
5. 需要记录压力样本时勾选“记录 CSV”。
6. 摄像头来源选择“本机摄像头”时填 `0`、`1` 等编号；选择“手机/IP 摄像头”时填 HTTP/MJPEG/RTSP 地址。
7. 点击“启动摄像头”后，上位机会提取光流趋势，并在串口连接时发送 `vision` v1 给 ESP32-S3。
8. 风险等级和气囊动作以 ESP32-S3 返回的 `risk` / `actuator` 为准。
9. 如果固件默认模拟 `vision_detect` 任务正在运行，界面会显示模拟 truck 目标和 v2 风险；这不是 PC 摄像头真实识别结果。

## 串口协议支持

### pressure v1

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

### vision v1

上位机发送给 ESP32-S3：

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

### vision_detect v1

上位机解析并显示 ESP32-S3 发来的检测事件。当前固件来源是 `source:"simulated"`。

```json
{"type":"vision_detect","version":1,"seq":42,"ts_ms":50000,"source":"simulated","objects":[{"class":"truck","confidence":0.85,"bbox":[100,60,80,60],"distance_m":5.2,"approaching":true}],"nearest_distance_m":5.2,"ttc_s":4.1,"valid":true}
```

### camera_status v1

Camera profile 的状态事件只用于健康展示；上位机不会接收或预览 JPEG，也不会把该事件视为真实目标检测。

```json
{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg","frame_bytes":18432,"fps":5.00,"frames_ok":12,"capture_failures":0,"psram":false,"valid":true}
```

### risk v1 / risk v2

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"risk","version":2,"seq":43,"ts_ms":50020,"level":40,"target_pct":40,"reason":"target_close","category":"vision_warning","nearest_class":"truck","nearest_distance_m":5.2,"ttc_s":4.1,"pressure_safe":true,"pressure_state":"safe"}
```

`sensor_overview_panel.py` 会在 v2 事件里显示 `category`、`nearest_class`、`nearest_distance_m` 和 `ttc_s`。

### actuator v1 / voice v1

```json
{"type":"actuator","version":1,"seq":43,"ts_ms":50030,"mode":"sim","target_pct":40,"pump":"inflate","valve":"closed"}
{"type":"voice","version":1,"seq":43,"ts_ms":50030,"text":"注意，truck接近","played":true}
```

`voice` 当前进入事件流和摘要，不是独立语音播放模块。

### motion

上位机保留 `motion` 解析和显示入口，但当前固件没有对应运行时数据源。

## 测试

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m compileall -q aix_host_app tests
```

当前测试覆盖：

- `pressure` NDJSON 和旧版 `PRESSURE` 日志解析。
- `risk` v1/v2、`actuator`、`motion`、`vision_detect`、`camera_status`、`voice` 解析。
- 上位机 voice 和 camera_status 事件路由到事件流/视觉面板。
- 坏行、缺字段和无效 JSON 处理。
- 气压历史缓存、模拟数据生成、X/Y 轴缩放策略。
- 摄像头配置、视觉事件发送桥和光流趋势分析器。

全部 Python 测试源码不再被忽略，提交时可纳入仓库。建议从仓库根目录运行统一验证：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 结构优化建议

1. `app.py` 只保留主窗口装配与顶层路由，串口、摄像头和记录分别交给控制器/服务。
2. 把 `models.py`、`parsers.py` 和发送编码归入 `protocol/`，并用独立协议文档约束版本、字段、方向和单位。
3. 把压力 CSV 扩展为统一事件记录器，覆盖 `pressure / vision_detect / risk / voice / actuator / fault`。
4. 为串口断开、摄像头断流、解析失败和固件事件超时提供统一状态模型，而不是只显示原始错误文本。
5. 保持 PC 摄像头分析器接口可替换；它是临时输入与调试工具，不应成为最终安全决策依赖。

## 安全边界

- 上位机可以生成临时 `vision` v1，但最终产品的视觉判断和执行决策应在 ESP32-S3 本地完成。
- 上位机展示的是调试和演示结果，不直接控制真实泵阀。
- 当前 `vision_detect` 显示来自固件模拟任务，不能当成真实摄像头识别能力。
- 当前 `target_pct` 和 `actuator` 是模拟输出，不能代表真实气囊已经可安全充放气。
