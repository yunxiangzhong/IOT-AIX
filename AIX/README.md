# AIX ESP32-S3 固件工程

这是 AIX 脉盔的 ESP-IDF 固件工程。当前固件已经实现压力采集、PC 光流视觉输入、模拟 `vision_detect` 输入、风险融合 v1/v2、`voice` 串口事件和 `actuator` 模拟动作。

当前还没有真实摄像头采集、真实目标检测、真实语音模块和真实泵阀控制。固件现在更准确的定位是：用真实气压传感器和模拟视觉事件验证安全闭环接口。

## 当前运行链路

```text
app_main
├─ pressure_sensor_start_task()
│  └─ 每 1000 ms 输出 pressure v1
├─ vision_input_start_task()
│  └─ 从 USB-UART stdin 接收 PC 光流 vision v1 和隐藏 config
├─ risk_fusion_start_task()
│  ├─ 优先读取 vision_detect snapshot，输出 risk v2
│  ├─ 没有有效 vision_detect 时 fallback 到 vision v1，输出 risk v1
│  ├─ 根据风险结果输出 actuator 模拟事件
│  └─ v2 风险达到阈值时输出 voice 事件
└─ vision_detect_input_start_task()
   └─ 默认模拟 truck 从远到近，输出 vision_detect v1 并写入 snapshot
```

因为 `vision_detect_input_start_task()` 现在默认启动，正常运行一小段时间后 `risk_fusion` 基本会走 v2 路径。PC 上位机发送的 `vision` v1 保留为 fallback，不是当前默认主风险源。

## 当前硬件目标

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| ESP32-S3-DevKitC-1 | 已使用 | 当前固件目标板 |
| XGZP6847A 气压传感器 | 已接入 | OUT 接 `GPIO1 / ADC1_CH0` |
| PC/手机摄像头外部视觉 | 已接入 | 上位机计算光流特征，经 USB-UART 发给 ESP32-S3 |
| 模拟 vision_detect | 已接入 | 固件内部模拟 truck 接近，用于 v2 协议闭环 |
| 气泵、电磁阀、气囊 | 未接入 | 当前只输出 `actuator` 模拟事件 |
| OV5640 / OV2640 摄像头 | 未接入 | 还没有 DVP 采集和帧处理代码 |
| YOLO / ESP-DL 检测 | 未接入 | 还没有真实目标检测模型 |
| 语音模块 | 未接入 | 当前只输出 `voice` 串口事件 |
| 双目/雷达/IMU | 未接入 | 后续扩展 |

## 目录结构

```text
AIX/
├─ main/
│  ├─ main.c                 # 固件入口和任务启动
│  ├─ pressure_sensor.c/h    # ADC 采样、校准、滤波、pressure 输出
│  ├─ config_input.c/h       # 隐藏 config 协议，压力默认开启
│  ├─ vision_input.c/h       # 接收 PC 光流 vision v1
│  ├─ vision_detect.c/h      # vision_detect 结构和字符串解析器
│  ├─ vision_detect_input.c/h
│  │                        # ESP 平台下的模拟 vision_detect 任务
│  ├─ distance_estimator.c/h # 单目测距、approaching、TTC 纯函数
│  ├─ risk_fusion.c/h        # v1 光流风险 + v2 检测风险
│  ├─ voice_prompt.c/h       # voice JSON 格式化和串口输出
│  ├─ airbag_control.c/h     # actuator 模拟输出
│  └─ CMakeLists.txt
├─ test/                     # 本地主机 GCC 测试，当前被 .gitignore 忽略
├─ CMakeLists.txt
├─ sdkconfig
└─ README.md
```

## 已实现功能

- 初始化 ESP32-S3 ADC1 CH0。
- 尝试启用 ESP-IDF ADC 校准，失败时回退到比例换算。
- 将 200 mV 到 2700 mV 映射到 0 kPa 到 200 kPa。
- 使用指数滤波平滑压力读数。
- 判断传感器电压有效性和 `180 kPa` 软过压。
- 默认启用压力监测，每 1000 ms 输出 `pressure` NDJSON。
- 从 USB-UART stdin 接收 PC 上位机发送的 `vision` v1。
- 支持隐藏 `config` JSON 切换压力监测，默认开启。
- 每 200 ms 模拟一个 `truck` 类型 `vision_detect` 事件。
- 每 50 ms 运行风险融合，开发阶段每 500 ms 输出风险事件。
- `risk_fusion` v1 支持 PC 光流阈值判断。
- `risk_fusion` v2 支持 `vision_detect + pressure`，输出 category、nearest_class、distance、TTC。
- 压力无效或过压时，风险可保持告警，但 `target_pct` 会钳制为 0。
- `voice_prompt` 输出 `voice` JSON，并对引号、反斜杠和常见控制字符做基础转义。
- `airbag_control` 输出 `actuator` 模拟事件，根据目标比例变化给出 inflate/hold/open。

## 未实现功能

- 没有 `camera_local.c/h`，没有真实摄像头初始化、采帧或降分辨率。
- 没有真实目标检测器，也没有 ESP-DL/YOLO 模型集成。
- `vision_detect_parse_line()` 是协议解析纯函数，当前运行时模拟任务不从串口读取外部 `vision_detect`。
- `distance_estimator` 还没有接入真实 bbox 测距链路。
- `voice_prompt` 没有接语音硬件。
- `airbag_control` 没有真实 GPIO/PWM/MOS 管/阀控输出。
- 没有人工急停、硬件限压、真实泄气策略验证。

## 风险融合规则

### v1：PC 光流 fallback

输入：

```text
vision: looming / area_rate / center_motion / confidence
pressure: enabled / valid / over_pressure
```

输出：

```text
level / target_pct / reason / vision_stale / pressure_state
```

主要阈值：

| 条件 | 输出 |
| --- | --- |
| `looming >= 0.90` 且 `area_rate >= 0.60` 且 `confidence >= 0.80` | `100%` |
| `looming >= 0.70` 且 `area_rate >= 0.35` 且 `confidence >= 0.70` | `80%` |
| `looming >= 0.45` 且 `area_rate >= 0.20` 且 `confidence >= 0.60` | `50%` |
| `looming >= 0.25` 且 `confidence >= 0.50` | `20%` |
| 视觉缺失、过期或无效 | `0%` |

### v2：vision_detect + pressure

输入：

```text
vision_detect: class / confidence / distance_m / approaching / ttc_s
pressure: enabled / valid / over_pressure
```

当前规则：

| 条件 | category | level | target_pct |
| --- | --- | --- | --- |
| 气压无效或过压 | `safety_stop` | 100 | 0 |
| 无目标或无有效检测 | `normal` | 10 | 10 |
| `ttc_s < 3.0` | `critical` | 100 | 100 |
| `nearest_distance_m < 5.0` | `vision_warning` | 40 | 40 |
| `nearest_distance_m < 15.0` | `vision_caution` | 20 | 20 |
| 更远目标 | `normal` | 10 | 10 |

## 串口事件

### pressure v1

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

### vision v1

PC 上位机发送：

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

### vision_detect v1

当前固件模拟任务输出：

```json
{"type":"vision_detect","version":1,"seq":42,"ts_ms":50000,"source":"simulated","objects":[{"class":"truck","confidence":0.85,"bbox":[100,60,80,60],"distance_m":5.2,"approaching":true}],"nearest_distance_m":5.2,"ttc_s":4.1,"valid":true}
```

### risk v1 / risk v2

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"risk","version":2,"seq":43,"ts_ms":50020,"level":40,"target_pct":40,"reason":"target_close","category":"vision_warning","nearest_class":"truck","nearest_distance_m":5.2,"ttc_s":4.1,"pressure_safe":true,"pressure_state":"safe"}
```

### voice v1 / actuator v1

```json
{"type":"voice","version":1,"seq":43,"ts_ms":50030,"text":"注意，truck接近","played":true}
{"type":"actuator","version":1,"seq":43,"ts_ms":50030,"mode":"sim","target_pct":40,"pump":"inflate","valve":"closed"}
```

## 关键参数

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `PRESSURE_SENSOR_ADC_GPIO` | `1` | XGZP6847A 输出接入 GPIO |
| `PRESSURE_SENSOR_MIN_MV` | `200` | 0 kPa 对应电压 |
| `PRESSURE_SENSOR_MAX_MV` | `2700` | 满量程对应电压 |
| `PRESSURE_SENSOR_FULL_SCALE_KPA` | `200.0` | 满量程压力 |
| `PRESSURE_SENSOR_OVER_PRESSURE_KPA` | `180.0` | 软过压阈值 |
| `PRESSURE_SENSOR_SAMPLE_PERIOD_MS` | `20` | 采样周期 |
| `PRESSURE_SENSOR_LOG_PERIOD_MS` | `1000` | pressure 上报周期 |
| `RISK_FUSION_PERIOD_MS` | `50` | 风险融合周期 |
| `RISK_FUSION_LOG_PERIOD_MS` | `500` | risk / actuator / voice 开发阶段输出周期 |
| `RISK_FUSION_VISION_STALE_MS` | `500` | PC `vision` v1 过期时间 |
| `VISION_DETECT_PERIOD_MS` | `200` | 模拟 `vision_detect` 输出周期 |

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

## 主机侧 C 测试

这些测试不依赖 ESP-IDF，可用本机 GCC 验证纯函数和协议逻辑。

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX

gcc -o D:\Projects\IOTCompetition\tmp\pressure_sensor_math_test.exe test\pressure_sensor_math_test.c -I main -Wall -Wextra -lm
D:\Projects\IOTCompetition\tmp\pressure_sensor_math_test.exe

gcc -o D:\Projects\IOTCompetition\tmp\vision_input_parse_test.exe main\vision_input.c test\vision_input_parse_test.c -I main -Wall -Wextra
D:\Projects\IOTCompetition\tmp\vision_input_parse_test.exe

gcc -o D:\Projects\IOTCompetition\tmp\config_input_parse_test.exe main\config_input.c test\config_input_parse_test.c -I main -Wall -Wextra
D:\Projects\IOTCompetition\tmp\config_input_parse_test.exe

gcc -o D:\Projects\IOTCompetition\tmp\vision_detect_parse_test.exe main\vision_detect.c test\vision_detect_parse_test.c -I main -Wall -Wextra
D:\Projects\IOTCompetition\tmp\vision_detect_parse_test.exe

gcc -o D:\Projects\IOTCompetition\tmp\distance_estimator_test.exe main\distance_estimator.c test\distance_estimator_test.c -I main -Wall -Wextra
D:\Projects\IOTCompetition\tmp\distance_estimator_test.exe

gcc -o D:\Projects\IOTCompetition\tmp\risk_fusion_test.exe main\risk_fusion.c main\vision_detect.c test\risk_fusion_test.c -I main -Wall -Wextra -lm
D:\Projects\IOTCompetition\tmp\risk_fusion_test.exe

gcc -o D:\Projects\IOTCompetition\tmp\voice_prompt_test.exe main\voice_prompt.c test\voice_prompt_test.c -I main -Wall -Wextra
D:\Projects\IOTCompetition\tmp\voice_prompt_test.exe
```

仓库当前 `.gitignore` 忽略 `AIX/test/`，所以本地测试文件默认不会被普通 `git add .` 提交。

## 下一步开发建议

1. 增加一个明确开关，控制是否启动模拟 `vision_detect`，避免它默认覆盖 PC `vision` v1 演示路径。
2. 接入 `camera_local.c/h`，先验证真实摄像头初始化、低分辨率采帧和错误状态输出。
3. 用固定假检测框接入 `distance_estimator`，确认距离、approaching 和 TTC 在运行时可用。
4. 再接轻量检测器，先限制类别和分辨率，避免 ESP32-S3 负载失控。
5. 接真实泵阀前，先实现 GPIO/PWM 层、过压停止、泄气策略和人工急停。
6. 语音硬件接入前，保留 `voice` JSON 作为上位机和答辩演示接口。

## 安全边界

- 当前 `vision_detect` 是模拟输入，不能代表真实道路识别能力。
- 摄像头识别和单目距离估计存在误差，第一版只能定位为风险提醒原型。
- 气压无效、过压、摄像头异常、检测置信度过低时，执行层必须保守处理。
- 真实气囊接入前，`target_pct` 和 `actuator` 都是模拟输出。
- 任何 100% 满充逻辑都必须经过硬件限压、泄气和人工急停策略验证。
