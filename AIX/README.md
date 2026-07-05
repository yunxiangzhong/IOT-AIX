# AIX ESP32-S3 固件工程

这是 AIX 脉盔的 ESP-IDF 固件工程。当前版本实现气囊压力传感器采集、滤波、状态判断和串口上报，为 PC 上位机可视化提供实时数据。

## 硬件目标

- 主控：ESP32-S3-DevKitC-1
- 压力传感器：XGZP6847A 气压传感器模块
- 供电：传感器使用 3.3 V
- 信号连接：传感器 `OUT` 接 ESP32-S3 `GPIO1 / ADC1_CH0`
- 串口监视：通过开发板 J4 USB-UART 连接 PC

## 目录结构

```text
AIX/
├─ main/
│  ├─ main.c             # 固件入口
│  ├─ pressure_sensor.c  # ADC 采样、校准、滤波、串口输出
│  └─ pressure_sensor.h  # 气压换算和数据结构
├─ test/
│  └─ pressure_sensor_math_test.c  # 可用主机 GCC 跑的换算测试
├─ CMakeLists.txt
├─ sdkconfig
└─ README.md
```

## 当前功能

- 初始化 ESP32-S3 ADC1 CH0。
- 尝试启用 ESP-IDF ADC 校准方案，失败时回退到原始比例换算。
- 将 200 mV 到 2700 mV 映射到 0 kPa 到 200 kPa。
- 使用指数滤波平滑压力读数。
- 判断传感器电压是否处于有效范围。
- 判断滤波压力是否超过软过压阈值 `180 kPa`。
- 每 500 ms 输出一行 NDJSON 压力事件，供上位机读取。

## 构建和烧录

需要先安装 ESP-IDF，并进入 ESP-IDF PowerShell 环境。

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
idf.py set-target esp32s3
idf.py build
idf.py flash monitor
```

如果只需要查看串口输出：

```powershell
idf.py monitor
```

## 串口输出格式

固件会输出普通 ESP-IDF 日志，同时每 500 ms 输出一行压力事件：

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

上位机只解析 `type=pressure` 的 JSON 行，其他日志会被忽略。

## 关键参数

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `PRESSURE_SENSOR_ADC_GPIO` | `1` | 传感器输出接入 GPIO |
| `PRESSURE_SENSOR_MIN_MV` | `200` | 0 kPa 对应电压 |
| `PRESSURE_SENSOR_MAX_MV` | `2700` | 满量程对应电压 |
| `PRESSURE_SENSOR_FULL_SCALE_KPA` | `200.0` | 满量程压力 |
| `PRESSURE_SENSOR_OVER_PRESSURE_KPA` | `180.0` | 软过压告警阈值 |
| `PRESSURE_SENSOR_SAMPLE_PERIOD_MS` | `20` | 采样周期 |
| `PRESSURE_SENSOR_LOG_PERIOD_MS` | `500` | 串口上报周期 |
| `PRESSURE_SENSOR_FILTER_ALPHA` | `0.2` | 指数滤波系数 |

## 主机侧数学测试

不依赖 ESP-IDF，可用本机 GCC 验证电压到压力的换算和阈值判断：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
gcc AIX\test\pressure_sensor_math_test.c -o D:\Projects\IOTCompetition\tmp\pressure_sensor_math_test.exe
D:\Projects\IOTCompetition\tmp\pressure_sensor_math_test.exe
```

退出码为 `0` 表示测试通过。

## Git 注意事项

`AIX/build/`、ESP-IDF 生成物和本地工具缓存不应上传到 GitHub。仓库根目录 `.gitignore` 已忽略常见构建产物；`AIX/.gitignore` 也保留了 ESP-IDF 工程相关规则。

## 后续扩展

- 增加摄像头模块后，可在固件或后续视觉处理模块中输出场景事件。
- 增加气泵、电磁阀和 PWM 控制后，可将压力反馈接入闭环控制。
- 将风险等级与预充气比例映射，例如 0%、20%、50%、80%、100%。
