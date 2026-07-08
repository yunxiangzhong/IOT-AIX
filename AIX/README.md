# AIX ESP32-S3 固件工程

这是 AIX 脉盔的 ESP-IDF 固件工程。当前版本已经实现气囊压力采集、PC 外部视觉输入、ESP32-S3 本地风险分级和气囊模拟动作上报；7.8 版本的下一步目标是接入单目摄像头端侧视觉链路，让 ESP32-S3 从“接收外部视觉特征”升级为“本地采集摄像头、轻量检测、估算距离、输出风险和执行动作”。

固件设计原则：安全关键判断和执行必须优先在 ESP32-S3 本地完成。PC 上位机只做调试、演示、记录和算法过渡，不作为最终安全执行控制器。

## 7.8 固件目标架构

```text
OV5640 / OV2640 摄像头
    |
    v
camera_local
    | 低分辨率图像 / 裁剪图像
    v
yolo_detector / esp_dl_detector
    | class / bbox / confidence
    v
distance_estimator
    | distance_m / approaching / ttc_s
    v
risk_fusion <----- pressure_sensor
    | target_pct / reason / category
    +----> voice_prompt
    |
    v
airbag_control
    |
    v
气泵 / 充气电磁阀 / 放气电磁阀 / 气囊
```

第一版推荐摄像头方案是 `OV5640 + ESP32-S3 + PSRAM`。`OV2640` 可作为低成本备选。双目摄像头、雷达、IMU 都先放入后续扩展，不作为 7.8 第一版主线。

## 当前硬件目标

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| ESP32-S3-DevKitC-1 | 已使用 | 当前固件目标板 |
| XGZP6847A 气压传感器 | 已接入 | OUT 接 `GPIO1 / ADC1_CH0` |
| PC/手机摄像头外部视觉 | 已接入 | 上位机计算视觉特征，经 USB-UART 发给 ESP32-S3 |
| 气泵、电磁阀、气囊 | 模拟阶段 | 当前只输出 `actuator` 模拟事件 |
| OV5640 单目摄像头 | 规划中 | 7.8 推荐主摄像头，需要 PSRAM 和稳定 DVP 接线 |
| OV2640 单目摄像头 | 备选 | 适合低成本验证，不作为展示上限方案 |
| 语音模块 | 规划中 | 先输出 `voice` 串口事件，后续接真实语音硬件 |
| 双目/雷达/IMU | 后续扩展 | 单目方案稳定后再评估 |

## 目录结构

```text
AIX/
├─ main/
│  ├─ main.c             # 固件入口和任务调度
│  ├─ pressure_sensor.c  # ADC 采样、校准、滤波、pressure 输出
│  ├─ vision_input.c     # 当前接收 PC 外部 vision / 隐藏 config 事件
│  ├─ risk_fusion.c      # 当前风险分级和目标充气比例
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

规划新增模块：

```text
main/
├─ camera_local.c/h          # OV5640/OV2640 DVP 摄像头采集和预处理
├─ yolo_detector.c/h         # 轻量 YOLO 或 ESP-DL 检测封装
├─ distance_estimator.c/h    # 单目粗测距、距离平滑和接近趋势
└─ voice_prompt.c/h          # 语音播报文本、冷却时间和 voice 事件
```

## 当前已实现功能

- 初始化 ESP32-S3 ADC1 CH0。
- 尝试启用 ESP-IDF ADC 校准方案，失败时回退到原始比例换算。
- 将 200 mV 到 2700 mV 映射到 0 kPa 到 200 kPa。
- 使用指数滤波平滑压力读数。
- 判断传感器电压是否处于有效范围。
- 判断滤波压力是否超过软过压阈值 `180 kPa`。
- 默认启用压力监测，每 1000 ms 输出一行 `pressure` NDJSON 事件。
- 从 USB-UART stdin 接收 PC 上位机发送的临时 `vision` 事件。
- 每 50 ms 运行风险融合，开发阶段每 500 ms 输出 `risk` 与 `actuator` 模拟事件。
- 视觉事件超过 500 ms 未更新时标记过期。
- 气压无效或过压时保留风险判断，但将目标充气比例钳制为 0。
- 保留隐藏 `config` 调试协议，上位机不提供可见关闭压力监测入口。

## 风险融合目标

### 当前 v1

当前 `risk_fusion` 只接收临时 `vision` 特征和压力安全状态：

```text
vision: looming / area_rate / center_motion / confidence
pressure: valid / over_pressure
output: level / target_pct / reason / pressure_state
```

### 7.8 v2

下一阶段目标是接收端侧 `vision_detect`：

```text
输入：
├─ vision_detect：目标类别、bbox、confidence、distance_m、approaching、ttc_s
└─ pressure：气囊内压、有效性、过压状态

输出：
├─ risk_level：0-100
├─ target_pct：10 / 20 / 40 / 100
├─ reason：truck_approaching / person_near / pressure_unsafe 等
├─ category：vision_caution / vision_warning / protection / safety_stop
├─ voice_text：语音播报文本
└─ actuator：气泵、电磁阀、泄气阀动作
```

建议第一版映射：

| 条件 | 风险 | 目标充气 |
| --- | --- | --- |
| 未检测到目标 | normal | 10% |
| 检测到车/人，但距离较远 | caution | 20% |
| 目标距离中等且持续接近 | warning | 40% |
| 目标很近或 TTC 小于 3 秒 | critical | 100% |
| 气压无效或过压 | safety_stop | 0%，停止继续充气 |

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

## 串口事件

### 已实现：pressure

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

### 已实现：临时外部 vision

PC 上位机发送：

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

ESP32-S3 返回：

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

## 关键参数

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `PRESSURE_SENSOR_ADC_GPIO` | `1` | XGZP6847A 输出接入 GPIO |
| `PRESSURE_SENSOR_MIN_MV` | `200` | 0 kPa 对应电压 |
| `PRESSURE_SENSOR_MAX_MV` | `2700` | 满量程对应电压 |
| `PRESSURE_SENSOR_FULL_SCALE_KPA` | `200.0` | 满量程压力 |
| `PRESSURE_SENSOR_OVER_PRESSURE_KPA` | `180.0` | 软过压告警阈值 |
| `PRESSURE_SENSOR_SAMPLE_PERIOD_MS` | `20` | 采样周期 |
| `PRESSURE_SENSOR_LOG_PERIOD_MS` | `1000` | 串口上报周期 |
| `PRESSURE_SENSOR_FILTER_ALPHA` | `0.2` | 指数滤波系数 |
| `RISK_FUSION_PERIOD_MS` | `50` | 风险融合周期 |
| `RISK_FUSION_LOG_PERIOD_MS` | `500` | 开发阶段 risk / actuator 上报周期 |
| `RISK_FUSION_VISION_STALE_MS` | `500` | 当前临时 vision 事件过期时间 |

## 摄像头和引脚规划

当前压力传感器已占用 `GPIO1 / ADC1_CH0`。摄像头接入需要重新核对 ESP32-S3-DevKitC-1 原理图、PSRAM/Flash 占用、启动保留引脚和外设复用限制。

| 模块 | 接口 | 状态 | 说明 |
| --- | --- | --- | --- |
| XGZP6847A 气压传感器 | ADC1_CH0 / GPIO1 | 已实现 | 需确认使用 3.3V 版本和合适量程 |
| OV5640 摄像头 | DVP | 规划中 | 推荐主摄像头，需 PSRAM，推理前降分辨率 |
| OV2640 摄像头 | DVP | 备选 | 低成本验证用 |
| 气泵 PWM | LEDC | 规划中 | 接 MOS 管驱动 |
| 充气电磁阀 | GPIO | 规划中 | 接 MOS 管驱动 |
| 放气电磁阀 | GPIO | 规划中 | 接 MOS 管驱动 |
| 语音模块 | UART / I2S / GPIO | 规划中 | 先用串口 `voice` 事件模拟 |
| PC 通信 | UART0 / USB-UART | 已使用 | 当前串口调试和上位机通信 |

建议：如果裸 DevKitC 接 DVP 摄像头接线风险较高，可以使用带摄像头接口和 PSRAM 的 ESP32-S3 视觉板作为视觉子节点，通过 UART/I2C 把 `vision_detect` 发给当前主控板；比赛口径仍保持 ESP32-S3 为主控和执行控制器。

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

后续新增 `vision_detect`、`distance_estimator`、`risk v2` 后，需要补充纯函数测试和协议解析测试。

## 下一步开发建议

1. 先确认硬件：OV5640 摄像头模块、ESP32-S3 PSRAM、DVP 接线方案。
2. 新增 `camera_local.c/h`，只做摄像头初始化、低分辨率采集和帧状态输出。
3. 新增 `distance_estimator.c/h` 的纯函数测试，先用模拟 bbox 验证距离估算和平滑。
4. 新增 `vision_detect` 数据结构和串口输出，先用假检测结果打通上位机显示。
5. 再接 `yolo_detector` 或 `esp_dl_detector`，控制类别数量和帧率。
6. 升级 `risk_fusion` 到 v2，接入 `vision_detect + pressure`。
7. 新增 `voice_prompt`，先输出 `voice` 事件，后续接真实语音模块。
8. 最后把 `airbag_control` 从模拟输出切换到真实气泵/电磁阀。

## Git 注意事项

`AIX/build/`、ESP-IDF 生成物和本地工具缓存不应上传到 GitHub。仓库根目录 `.gitignore` 已忽略常见构建产物；`AIX/.gitignore` 也保留了 ESP-IDF 工程相关规则。

## 安全边界

- 摄像头识别和单目距离估计存在误差，第一版定位为风险提醒原型。
- 气压无效、过压、摄像头异常、检测置信度过低时，执行层必须保守处理。
- 真实气囊接入前，`target_pct` 和 `actuator` 都是模拟输出。
- 任何 100% 满充逻辑都必须经过硬件限压、泄气和人工急停策略验证。
