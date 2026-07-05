# AIX 脉盔上位机

这是脉盔项目的 PC 端可视化程序，独立于 ESP-IDF 固件工程。

## 功能

- 读取 ESP32-S3 串口 NDJSON 气压数据。
- 实时显示原始气压、滤波气压、ADC 原始值、电压、有效性和过压状态。
- 保留旧版 `PRESSURE,seq=...` 日志解析，方便过渡。
- 提供模拟数据模式，未连接开发板时也能检查界面。
- 预留摄像头画面、场景识别、目标识别和风险等级区域。
- 可选记录 CSV，文件写入 `logs/`。

## 安装

在 `D:\Projects\IOTCompetition\ProjectFile\host_app` 目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 运行

```powershell
python -m aix_host_app
```

如果没有开发板，勾选左侧“模拟数据”即可查看气压曲线。

## 固件串口数据格式

固件每 500 ms 输出一行压力事件：

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

上位机会忽略普通 ESP-IDF 日志和其他非压力事件。

## 后续扩展点

- 摄像头图传接入后，新增图像源模块，向右侧视觉面板推送帧。
- 路口、车辆、行人等算法结果可封装为 `RiskEvent`。
- 云端大模型建议可以作为非安全关键事件进入事件流，不参与本地紧急防护闭环。
