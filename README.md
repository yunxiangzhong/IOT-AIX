# AIX 脉盔

AIX 脉盔是一套面向电动车和摩托车骑行安全的智能头盔原型。当前工程聚焦气囊压力感知与 PC 上位机可视化，后续环境感知路线按“摄像头模块 + 算法实时分析路况”扩展。

## 项目结构

```text
ProjectFile/
├─ AIX/                 # ESP32-S3 ESP-IDF 固件工程
├─ host_app/            # Python 桌面上位机
├─ README.md            # 本文件，GitHub 项目总览
└─ .gitignore           # 仓库级忽略规则
```

## 当前能力

- ESP32-S3 读取 XGZP6847A 气压传感器模拟电压。
- 固件完成 ADC 校准、kPa 换算、指数滤波、有效性判断和过压判断。
- 固件通过串口输出 NDJSON 压力事件，便于上位机解析。
- Python 上位机实时显示原始气压、滤波气压、ADC 原始值、电压、状态和事件流。
- 上位机支持模拟数据、CSV 记录、动态 Y 轴缩放、横向自动跟随开关。
- 上位机已预留摄像头画面、场景识别、目标识别和风险等级区域。

## 快速开始

### 1. 固件

进入 ESP-IDF 工程：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
idf.py build
idf.py flash monitor
```

当前目标板为 ESP32-S3-DevKitC-1，气压传感器 OUT 接 GPIO1 / ADC1_CH0。

### 2. 上位机

进入上位机目录：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m aix_host_app
```

如果暂时没有连接开发板，可以勾选“模拟数据”查看曲线和界面状态。

## 串口数据格式

固件每 500 ms 输出一行压力事件：

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

上位机也兼容早期 `PRESSURE,seq=...` 日志格式，便于调试过渡。

## Git 上传约定

本仓库只上传源码、配置、文档和 `requirements.txt`。

不要上传：

- Python 虚拟环境：`.venv/`、`venv/`、`env/`
- Python 缓存：`__pycache__/`、`*.pyc`
- ESP-IDF 构建目录：`AIX/build/`
- 本地日志和上位机 CSV 输出：`host_app/logs/`
- 本地工具缓存和系统临时文件

## 后续方向

- 接入摄像头模块，展示实时画面或图传帧。
- 将路口、车辆、行人、侧后方接近等算法结果封装为风险事件。
- 将风险等级映射到气囊预充气策略，例如 0%、20%、50%、80%、100%。
- 云端大模型只用于非安全关键的骑行复盘、参数建议和事件说明，本地控制闭环保持端侧独立。
