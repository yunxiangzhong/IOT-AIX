# AIX 脉盔

AIX 脉盔是一套面向电动车、摩托车骑行场景的智能安全头盔原型。项目目标不是只在碰撞后被动保护，而是在骑行过程中用摄像头识别前方或侧方风险目标，结合距离估计和气囊压力反馈，让骑手提前听到提醒、感受到头部压力变化，并在紧急场景下进入气囊保护状态。

当前 7.8 版本的主线已经收敛为：

```text
摄像头采集
    -> ESP32-S3 端侧轻量目标检测
    -> 获取目标类别、方位、距离估计、接近趋势
    -> risk_fusion 生成风险等级和目标充气比例
    -> voice_prompt 语音提醒
    -> airbag_control 控制气泵、电磁阀和气囊
```

第一版推荐使用 `OV5640 + ESP32-S3 + PSRAM`。`OV2640` 可作为低成本验证方案，双目摄像头暂不作为必须项，只作为后续距离精度升级方向。

## 产品定位

### 核心卖点

| 卖点 | 触发场景 | 用户感知 |
| --- | --- | --- |
| 舒适低压支撑 | 正常骑行、无明显风险 | 气囊维持约 10% 低压，不明显打扰 |
| 安全意识反馈 | 检测到车辆、行人、障碍物接近，或距离持续缩短 | 气囊充到 20%-40%，形成明确压力提醒，同时语音播报 |
| 紧急主动保护 | 目标过近、TTC 很短、碰撞风险高 | 气囊快速满充到 100%，进入保护状态 |

风险映射建议：

```text
normal   -> 10%  舒适低压
caution  -> 20%  轻提醒
warning  -> 40%  明显提醒
critical -> 100% 紧急保护
```

## 系统架构

```text
感知层
├─ OV5640 单目摄像头：推荐主摄像头，采集车辆、行人、障碍物画面
├─ OV2640 单目摄像头：低成本备选，用于快速验证采集和检测链路
├─ PC/手机摄像头：当前已实现的临时输入，用于调试和演示
└─ 双目/外部视觉模块：后续扩展，不作为第一版必须项

ESP32-S3 视觉处理层
├─ camera_local：采集摄像头图像，降分辨率到推理输入
├─ yolo_detector / esp_dl_detector：轻量目标检测
├─ distance_estimator：基于目标框和标定参数做单目粗测距
└─ vision_detect：输出目标类别、bbox、confidence、distance_m、approaching

ESP32-S3 决策与执行层
├─ risk_fusion：融合视觉检测、距离趋势和气压安全状态
├─ pressure_sensor：XGZP6847A 气囊内压采集、滤波、过压保护
├─ voice_prompt：语音播报方向、目标和风险
└─ airbag_control：控制气泵、电磁阀、泄气阀和气囊目标压力

PC 上位机验证层
├─ 串口读取 pressure / risk / actuator，规划读取 vision_detect / voice
├─ 当前可用 PC/手机摄像头生成临时 vision 事件
├─ 展示压力曲线、风险等级、视觉结果、气囊动作和事件流
└─ 记录调试数据，服务比赛演示和参数复盘
```

## 当前实现状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| ESP32-S3 固件工程 | 已建立 | 位于 `AIX/`，使用 ESP-IDF |
| XGZP6847A 气压采集 | 已实现 | ADC1_CH0 / GPIO1，含校准、滤波、有效性和过压判断 |
| PC 外部视觉输入 | 已实现 | 上位机从本机/网络摄像头提取 `looming`、`area_rate`、`center_motion` |
| ESP 风险融合 v1 | 已实现 | 当前融合外部 `vision` 和压力安全状态 |
| 气囊控制 v1 | 已实现模拟输出 | 当前输出 `actuator` 模拟事件，尚未驱动真实泵阀 |
| 上位机 | 已实现第一版 | PySide6 界面、串口、曲线、视觉面板、事件流、CSV |
| OV5640 端侧摄像头 | 规划中 | 7.8 主线，新增 `camera_local.c/h` |
| 轻量目标检测 | 规划中 | 新增 `yolo_detector.c/h` 或 `esp_dl_detector.c/h` |
| 单目距离估计 | 规划中 | 新增 `distance_estimator.c/h`，输出距离和接近趋势 |
| 语音播报 | 规划中 | 新增 `voice_prompt.c/h`，先串口模拟，再接真实语音模块 |
| 真实气泵/电磁阀闭环 | 规划中 | 接入 PWM、MOS 管、PID 和失效安全策略 |
| 双目/雷达/IMU | 后续扩展 | 不作为 7.8 第一版主线 |

## 项目结构

```text
ProjectFile/
├─ AIX/                 # ESP32-S3 ESP-IDF 固件工程
├─ host_app/            # Python / PySide6 桌面上位机
├─ README.md            # 项目总览
└─ .gitignore           # 仓库级忽略规则
```

## 数据接口

### 已实现：pressure

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

### 已实现：临时外部 vision

当前由 PC 上位机发送给 ESP32-S3，用于在真实摄像头模块接入前验证风险融合链路。

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

### 已实现：risk v1 / actuator v1

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"actuator","version":1,"seq":35,"ts_ms":43100,"mode":"sim","target_pct":80,"pump":"hold","valve":"closed"}
```

### 规划中：vision_detect

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

### 规划中：risk v2 / voice

```json
{"type":"risk","version":2,"seq":43,"ts_ms":50020,"level":40,"target_pct":40,"reason":"truck_approaching","category":"vision_warning","nearest_class":"truck","nearest_distance_m":5.2,"ttc_s":4.1,"pressure_safe":true,"pressure_state":"safe"}
{"type":"voice","version":1,"seq":43,"ts_ms":50030,"text":"前方大货车接近，请减速","played":true}
```

## 快速开始

### 固件

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
idf.py set-target esp32s3
idf.py build
idf.py flash monitor
```

当前已接入的压力传感器默认使用 ESP32-S3 `GPIO1 / ADC1_CH0`。需要在 ESP-IDF PowerShell 或 VSCode ESP-IDF 终端中运行 `idf.py`。

### 上位机

本项目只保留一套虚拟环境：

```text
D:\Projects\IOTCompetition\ProjectFile\.venv
```

首次安装或更新依赖：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd .\host_app
python -m pip install -r requirements.txt
```

运行上位机推荐使用脚本：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\run_host_app.cmd
```

未连接开发板时，可以勾选“模拟数据”检查界面和曲线状态。

## 开发规划

### 阶段一：单目端侧视觉闭环

- 采购或准备 `OV5640 + ESP32-S3 + PSRAM` 摄像头链路。
- 新增 `camera_local.c/h`，接入 `esp32-camera`，采集低分辨率图像。
- 新增 `yolo_detector.c/h` 或 `esp_dl_detector.c/h`，跑通少类别轻量检测。
- 新增 `distance_estimator.c/h`，基于 bbox 宽度做粗测距和接近趋势判断。
- 将 `risk_fusion` 从临时 `vision` 阈值升级到 `vision_detect + pressure`。
- 上位机同步展示目标类别、bbox、距离、TTC、风险和气囊目标。

### 阶段二：语音与真实气囊执行

- 新增 `voice_prompt.c/h`，先用串口 `voice` 事件模拟语音播报。
- 接入真实语音模块、蜂鸣器或蓝牙音频方案。
- 将 `airbag_control` 从模拟输出切换为真实气泵和电磁阀控制。
- 使用 XGZP6847A 做内压闭环，标定 10%、20%、40%、100% 对应压力。

### 阶段三：稳定性和比赛演示

- 完善压力无效、过压、摄像头无帧、检测置信度低等失效安全策略。
- 固化演示场景：前方大货车接近、侧方车辆接近、行人/障碍物出现。
- 记录视觉、风险、压力、执行动作，支持赛后复盘和答辩展示。

### 阶段四：后续扩展

- 如果单目距离误差不够，再考虑 ToF、毫米波、超声波或双目模块。
- 如果 ESP32-S3 本地 YOLO 性能不足，可加视觉协处理模块，但 ESP32-S3 仍保持主控和执行闭环。
- IMU 可后续补充急加速、急刹车、急转弯和跌倒检测。

## 硬件选择建议

| 硬件 | 建议 |
| --- | --- |
| 摄像头 | 优先 OV5640，OV2640 只做低成本备选 |
| 主控 | ESP32-S3，必须确认 PSRAM |
| 气压传感器 | XGZP6847A，当前已按 3.3V 版本接入 GPIO1 / ADC1_CH0 |
| 执行机构 | 气泵 + 充气电磁阀 + 放气电磁阀 + MOS 管 |
| 语音输出 | 第一版可串口模拟，后续接语音模块或蓝牙音频 |
| 双目模块 | 暂缓采购，作为距离精度升级项 |

## 验证命令

上位机测试：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m unittest discover -s tests
..\.venv\Scripts\python.exe -m compileall -q aix_host_app tests
```

固件侧纯函数测试可在仓库根目录用 GCC 编译，详见 `AIX/README.md`。

## Git 上传约定

本仓库只上传源码、配置、文档和依赖清单。

不要上传：

- Python 虚拟环境：`.venv/`、`venv/`、`env/`
- Python 缓存：`__pycache__/`、`*.pyc`
- ESP-IDF 构建目录：`AIX/build/`
- 上位机日志和 CSV：`host_app/logs/`
- 本地工具缓存、串口日志和系统临时文件

## 安全边界

- 安全关键闭环必须优先在 ESP32-S3 本地完成。
- PC 上位机用于调试、演示和数据记录，不作为最终安全执行控制器。
- 摄像头识别和单目距离估计存在误差，第一版应定位为“风险提醒原型”，不能包装成自动避撞系统。
- 过压、压力传感器无效、摄像头异常、通信异常时，必须停止继续充气或进入安全泄气策略。
