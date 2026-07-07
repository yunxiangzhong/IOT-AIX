# AIX 脉盔

AIX 脉盔是一套面向电动车和摩托车骑行安全的智能头盔原型。项目核心不是“碰撞后触发”，而是把环境风险转换成连续的气囊预充气状态，让骑手通过头部压力变化直接感知风险，并在碰撞前提前进入防护准备。

当前代码仓库聚焦 ESP32-S3 端的本地安全闭环，以及 PC 上位机的数据验证与演示。当前阶段暂时没有真实摄像头、速度、加速度、IMU 或雷达模块；PC 摄像头作为临时视觉传感器替身，用光流扩张、中心运动和前景面积变化提取图像接近趋势特征并通过 USB-UART 发给 ESP32-S3，最终风险等级和气囊策略仍由 ESP32-S3 输出。

## 顶层设计

```text
环境感知层
├─ 当前临时输入：PC 本机摄像头 / 手机 IP 摄像头
├─ 后续真实模块：摄像头模块、速度模块、加速度模块、IMU、毫米波雷达
├─ 当前输出：vision 趋势特征 NDJSON
└─ 后续输出：motion、姿态、距离、TTC、目标类别等非直接执行信号

控制与采集层
├─ ESP32-S3-DevKitC-1
├─ XGZP6847A 气压传感器 ADC 采样，默认启用压力监测
├─ vision_input：接收 PC 摄像头临时传感器事件
├─ risk_fusion：每 50 ms 本地融合视觉趋势和压力安全状态
├─ airbag_control：当前仅输出气囊模拟动作
└─ 后续：气泵、电磁阀、PWM、PID 气动闭环

PC 验证与演示层
├─ 双向串口：接收 pressure / risk / actuator / motion，发送 vision
├─ 传感器总览：压力、速度、加速度、ESP 风险、气囊目标
├─ 压力曲线、运动模块占位、视觉闭环调试、事件流
└─ CSV 记录：当前只记录压力样本

安全边界
├─ 本地端侧规则负责安全关键动作
└─ 云端/大模型只做骑行复盘、参数建议、说明文本，不参与紧急控制闭环
```

设计原则：

- 安全关键闭环优先放在 ESP32-S3 或本地端侧，不依赖云端网络响应。
- 上位机是比赛调试和演示工具，不直接承担最终产品的安全控制职责。
- PC 摄像头只是临时视觉传感器替身，不是最终控制器。
- 速度、加速度模块目前只做 UI 和协议预留，不伪造输入，不参与风险融合。
- 气囊执行当前为模拟输出，真实泵阀接入前不得误驱动硬件。

## 项目结构

```text
ProjectFile/
├─ AIX/                 # ESP32-S3 ESP-IDF 固件工程
├─ host_app/            # Python / PySide6 桌面上位机
├─ README.md            # 本文件，项目总览
└─ .gitignore           # 仓库级忽略规则
```

## 当前能力

- ESP32-S3 读取 XGZP6847A 气压传感器模拟电压，默认启用压力监测。
- 固件完成 ADC 校准、kPa 换算、指数滤波、有效性判断和过压判断。
- 固件通过串口输出 NDJSON 压力事件，开发阶段默认 1000 ms 输出一行。
- PC 摄像头用 OpenCV 光流提取 `looming`、`area_rate`、`center_motion`、`confidence`。
- 上位机每 100 ms 最多发送一条 `vision` 事件给 ESP32-S3。
- ESP32-S3 每 50 ms 运行风险融合，开发阶段每 500 ms 输出 `risk` 和 `actuator` 事件。
- 上位机显示传感器总览、压力曲线、运动模块占位、视觉画面、视觉特征、ESP 风险原因、气囊模拟动作和事件流。
- 上位机支持模拟数据、CSV 记录、动态 Y 轴缩放、横向自动跟随开关。

## 快速开始

### 1. 固件

进入 ESP-IDF 工程：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
idf.py build
idf.py flash monitor
```

当前目标板为 ESP32-S3-DevKitC-1，气压传感器 OUT 接 GPIO1 / ADC1_CH0。需要在 ESP-IDF PowerShell 或 VSCode ESP-IDF 终端中运行 `idf.py`。

### 2. 上位机

本项目只保留一套虚拟环境：`D:\Projects\IOTCompetition\ProjectFile\.venv`。

首次安装或更新依赖：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd .\host_app
python -m pip install -r requirements.txt
```

运行上位机推荐使用脚本，避免误用 conda 的 `(base)` 环境：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\run_host_app.cmd
```

如果暂时没有连接开发板，可以勾选“模拟数据”查看曲线和界面状态。

## 数据接口

### 压力事件

固件默认启用压力监测，每 1000 ms 输出一行压力事件：

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

上位机也兼容早期 `PRESSURE,seq=...` 日志格式，便于调试过渡。

### 视觉输入

PC 摄像头临时替代真实摄像头模块时，上位机向 ESP32-S3 发送：

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

当前 `looming` 由光流扩张、中心运动和前景面积变化加权生成，不做人员、车辆或物体类别识别。

### 风险与气囊模拟事件

ESP32-S3 返回本地融合后的风险与气囊模拟动作：

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"actuator","version":1,"seq":35,"ts_ms":43100,"mode":"sim","target_pct":80,"pump":"hold","valve":"closed"}
```

`pressure_state` 当前可为 `safe`、`unsafe`、`disabled`。上位机不再提供可见的压力监测关闭开关，`disabled` 仅保留给隐藏调试配置。

### 运动模块预留

后续速度、加速度模块建议通过 `motion` 事件进入上位机，当前仅预留 UI 显示，不参与风险融合：

```json
{"type":"motion","version":1,"seq":1,"ts_ms":1000,"speed_mps":0.0,"accel_mps2":0.0,"speed_valid":false,"accel_valid":false}
```

## 验证命令

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m unittest discover -s tests
..\.venv\Scripts\python.exe -m compileall -q aix_host_app tests
```

主机侧 C 测试可在仓库根目录用 GCC 运行，用于验证固件纯函数解析和风险分级逻辑。

## VSCode ESP-IDF 插件配置

本仓库不提交 `.vscode/`，因为 VSCode 配置里通常包含本机 ESP-IDF 安装路径、串口号、clangd 路径和构建目录。这些内容每台电脑都不同，上传到 GitHub 反而容易导致他人环境出错。

推荐使用 VSCode 插件 **Espressif IDF** 重新生成本地配置：

1. 安装 VSCode 插件：在扩展市场搜索 `ESP-IDF`，安装 Espressif 官方插件。
2. 打开工程目录：用 VSCode 打开 `D:\Projects\IOTCompetition\ProjectFile\AIX`。
3. 配置插件：按 `Ctrl+Shift+P`，执行 `ESP-IDF: Configure ESP-IDF Extension`。
4. 设置目标芯片：执行 `ESP-IDF: Set Espressif Device Target`，选择 `esp32s3`。
5. 选择串口：执行 `ESP-IDF: Select Port to Use`，选择开发板对应的 COM 口。
6. 构建烧录：可使用插件侧边栏按钮，或在终端运行 `idf.py build`、`idf.py flash monitor`。

## Git 上传约定

本仓库只上传源码、配置、文档和 `requirements.txt`。

不要上传：

- Python 虚拟环境：`.venv/`、`venv/`、`env/`
- Python 缓存：`__pycache__/`、`*.pyc`
- ESP-IDF 构建目录：`AIX/build/`
- 本地日志和上位机 CSV 输出：`host_app/logs/`
- 本地工具缓存和系统临时文件

## 后续方向

- 切换到真实摄像头模块，复用现有视觉输入接口展示实时画面或图传帧。
- 接入速度、加速度、IMU、雷达后，将运动状态、目标距离、姿态补偿和 TTC 合成为风险等级。
- 将风险等级映射到真实气囊预充气策略，例如 0%、20%、50%、80%、100%。
- 接入气泵、电磁阀、MOS 管和 PWM 后，把 `airbag_control` 从模拟输出替换为硬件驱动。
- 云端大模型只用于非安全关键的骑行复盘、参数建议和事件说明，本地控制闭环保持端侧独立。
