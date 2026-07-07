# AIX ESP32-S3 固件工程

这是 AIX 脉盔的 ESP-IDF 固件工程。当前版本实现气囊压力传感器采集、PC 摄像头视觉特征接收、风险分级和气囊模拟动作上报，为“视觉趋势 -> ESP 本地决策 -> PC 可视化”闭环提供验证基础。

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
│  ├─ pressure_sensor.c  # ADC 采样、校准、滤波、pressure 输出
│  ├─ vision_input.c     # 接收 PC 摄像头 vision / 隐藏 config 事件
│  ├─ risk_fusion.c      # 本地风险分级和目标预充气比例
│  ├─ airbag_control.c   # 当前仅输出气囊模拟 actuator 事件
│  ├─ config_input.c     # 压力监测隐藏调试配置，默认开启
│  └─ *.h                # 对应头文件
├─ test/
│  ├─ pressure_sensor_math_test.c
│  ├─ vision_input_parse_test.c
│  ├─ risk_fusion_test.c
│  └─ config_input_parse_test.c
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
- 默认启用压力监测，每 1000 ms 输出一行 NDJSON 压力事件。
- 从 USB-UART stdin 接收 PC 摄像头 `vision` 事件。
- 每 50 ms 运行风险融合，开发阶段每 500 ms 输出 `risk` 与 `actuator` 模拟事件。
- 视觉事件超过 500 ms 未更新时标记过期；气压无效或过压时禁止继续升高目标充气比例。
- 保留隐藏 `config` 调试协议，但上位机不再提供关闭压力监测的可见开关。

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

固件会输出普通 ESP-IDF 日志，同时每 1000 ms 输出一行压力事件：

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

上位机只解析支持的 JSON 事件和旧版压力日志，其他日志会被忽略。

## 视觉触发闭环事件

PC 上位机发送给 ESP32-S3：

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

ESP32-S3 返回风险和气囊模拟动作：

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"actuator","version":1,"seq":35,"ts_ms":43100,"mode":"sim","target_pct":80,"pump":"hold","valve":"closed"}
```

## 风险分级规则

| 等级 | 默认条件 |
| --- | --- |
| 0 | 视觉过期、无效，或接近趋势不足 |
| 20 | `looming >= 0.25` 且 `confidence >= 0.50` |
| 50 | `looming >= 0.45` 且 `area_rate >= 0.20` 且 `confidence >= 0.60` |
| 80 | `looming >= 0.70` 且 `area_rate >= 0.35` 且 `confidence >= 0.70` |
| 100 | `looming >= 0.90` 且 `area_rate >= 0.60` 且 `confidence >= 0.80` |

压力无效或过压时，ESP 会保留视觉风险等级，但把目标充气比例钳制为 0。

## 压力监测默认策略

固件默认启用压力监测。`config` 协议仍保留为隐藏调试接口，但上位机不再提供关闭压力监测的可见开关。

PC 如需调试隐藏配置，可发送：

```json
{"type":"config","version":1,"pressure_enabled":true}
```

## 关键参数

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `PRESSURE_SENSOR_ADC_GPIO` | `1` | 传感器输出接入 GPIO |
| `PRESSURE_SENSOR_MIN_MV` | `200` | 0 kPa 对应电压 |
| `PRESSURE_SENSOR_MAX_MV` | `2700` | 满量程对应电压 |
| `PRESSURE_SENSOR_FULL_SCALE_KPA` | `200.0` | 满量程压力 |
| `PRESSURE_SENSOR_OVER_PRESSURE_KPA` | `180.0` | 软过压告警阈值 |
| `PRESSURE_SENSOR_SAMPLE_PERIOD_MS` | `20` | 采样周期 |
| `PRESSURE_SENSOR_LOG_PERIOD_MS` | `1000` | 串口上报周期 |
| `PRESSURE_SENSOR_FILTER_ALPHA` | `0.2` | 指数滤波系数 |
| `RISK_FUSION_PERIOD_MS` | `50` | 风险融合周期 |
| `RISK_FUSION_LOG_PERIOD_MS` | `500` | 开发阶段 risk / actuator 上报周期 |
| `RISK_FUSION_VISION_STALE_MS` | `500` | 视觉事件过期时间 |

## 主机侧 C 测试

不依赖 ESP-IDF，可用本机 GCC 验证纯函数和解析逻辑：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
gcc AIX\test\pressure_sensor_math_test.c -o D:\Projects\IOTCompetition\tmp\pressure_sensor_math_test.exe
gcc AIX\test\risk_fusion_test.c AIX\main\risk_fusion.c -o D:\Projects\IOTCompetition\tmp\risk_fusion_test.exe
gcc AIX\test\vision_input_parse_test.c AIX\main\vision_input.c -o D:\Projects\IOTCompetition\tmp\vision_input_parse_test.exe
gcc AIX\test\config_input_parse_test.c AIX\main\config_input.c -o D:\Projects\IOTCompetition\tmp\config_input_parse_test.exe
```

退出码为 `0` 表示测试通过。

## Git 注意事项

`AIX/build/`、ESP-IDF 生成物和本地工具缓存不应上传到 GitHub。仓库根目录 `.gitignore` 已忽略常见构建产物；`AIX/.gitignore` 也保留了 ESP-IDF 工程相关规则。

## 后续扩展

- 增加真实摄像头模块后，可在固件或后续视觉处理模块中输出场景事件。
- 增加速度、加速度、IMU、雷达模块后，再扩展风险融合输入。
- 增加气泵、电磁阀和 PWM 控制后，可将压力反馈接入真实闭环控制。
- 将风险等级与预充气比例映射到真实执行策略，例如 0%、20%、50%、80%、100%。
