# AIX 脉盔上位机

这是 AIX 脉盔项目的 PC 端可视化程序，独立于 ESP-IDF 固件工程。它用于比赛调试和演示阶段，当前主要显示气囊压力数据，并为后续摄像头环境感知预留界面和数据结构。

## 功能

- 读取 ESP32-S3 串口 NDJSON 气压数据。
- 实时显示原始气压、滤波气压、ADC 原始值、电压、有效性和过压状态。
- 兼容旧版 `PRESSURE,seq=...` 日志，便于从早期固件过渡。
- 气压曲线支持动态 Y 轴缩放，低压小波动也能看清楚。
- 气压曲线支持“自动跟随”按钮：开启时横轴跟随最新样本，关闭后可手动拖拽查看历史。
- 提供模拟数据模式，未连接开发板时也能检查界面。
- 可选记录 CSV，文件写入本地 `logs/`，该目录不会上传到 GitHub。
- 预留摄像头画面、场景识别、目标识别和风险等级区域。

## 目录结构

```text
host_app/
├─ aix_host_app/        # 上位机源码
│  ├─ widgets/          # 界面模块
│  ├─ app.py            # 主窗口
│  ├─ serial_source.py  # 串口读取线程
│  ├─ parsers.py        # 串口数据解析
│  ├─ models.py         # 数据模型
│  └─ plot_scaling.py   # 曲线视窗缩放策略
├─ tests/               # 单元测试
├─ requirements.txt     # Python 依赖清单
└─ README.md
```

## 安装

在 `D:\Projects\IOTCompetition\ProjectFile\host_app` 目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

只提交 `requirements.txt`，不要提交 `.venv/`。根目录 `.gitignore` 已忽略虚拟环境和 Python 缓存。

## 运行

```powershell
python -m aix_host_app
```

使用方式：

1. 选择 ESP32-S3 对应串口。
2. 波特率保持与固件监视器一致，默认可先用 `115200`。
3. 点击“连接”。
4. 若没有开发板，勾选“模拟数据”。
5. 需要记录时勾选“记录 CSV”。
6. 查看历史数据时关闭“自动跟随”，拖拽或缩放曲线；回到最新数据时重新开启。

## 固件串口数据格式

固件每 500 ms 输出一行压力事件：

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
python -m unittest discover -s tests
python -m compileall -q aix_host_app tests
```

测试覆盖：

- 新版 NDJSON 解析。
- 旧版 `PRESSURE` 日志解析。
- 坏行和缺字段处理。
- 气压历史缓存。
- 模拟数据生成。
- X/Y 轴动态缩放策略。

## 后续扩展点

- 摄像头图传接入后，新增图像源模块，向右侧视觉面板推送帧。
- 路口、车辆、行人等算法结果可封装为 `RiskEvent`。
- 云端大模型建议可以作为非安全关键事件进入事件流，不参与本地紧急防护闭环。
