# AIX 脉盔

AIX 脉盔是一套面向电动车、摩托车骑行场景的智能安全头盔原型。目标是把气囊压力反馈、视觉风险判断、语音提醒和气囊执行串成一条可演示、可调试的闭环。

这份 README 按 2026-07-10 当前仓库代码描述。P1 已加入 OV5640 初始化和 JPEG 采帧代码，但尚未在实机上验收；不把真实目标识别、语音硬件或泵阀控制写成已完成。完整审阅和优化建议见 [`docs/项目审阅与优化建议.md`](docs/项目审阅与优化建议.md)，接线见 [`docs/hardware/ov5640-devkitc1-wiring.md`](docs/hardware/ov5640-devkitc1-wiring.md)。

## 当前真实状态

当前代码能跑通的是“压力采集 + 串口事件 + 模拟视觉检测 + 风险融合 + 语音事件 + 气囊模拟动作”的原型链路。

```text
XGZP6847A 气压传感器
    -> ESP32-S3 pressure_sensor
    -> pressure NDJSON
    -> PC 上位机显示压力和曲线

ESP32-S3 内部模拟 vision_detect
    -> risk_fusion v2
    -> risk v2 / voice / actuator NDJSON
    -> PC 上位机显示目标检测、风险、动作和事件流

PC/手机摄像头
    -> host_app 光流趋势分析
    -> vision v1 NDJSON 发给 ESP32-S3
    -> risk_fusion v1 fallback

OV5640（Camera profile）
    -> camera_local QVGA JPEG 验证
    -> camera_status NDJSON
    -> PC 状态显示（不传图片、不产生 vision_detect）
```

需要特别注意：Demo 配置默认启动 `vision_detect_input` 模拟任务，所以新鲜且有效的模拟检测会优先走 v2 路径；Hardware 配置会关闭它。v2 快照达到或超过 500 ms 后会回退到 PC `vision` v1；若两条视觉链路都不可用，气囊目标为 0%。

## 2026-07-10 审阅结论

当前项目适合定位为“比赛演示和算法接口验证原型”，已有架构方向基本合理，不需要更换 ESP32-S3 主控或整体重写。本轮已完成测试可复现、Demo/Hardware/Camera profile、v2 超时降级和 OV5640 最小采帧代码；下一步是原生 ESP-IDF 环境下的相机实机验收，再逐步接检测与执行安全状态机。

## 还没有完成的部分

- OV5640 尚未完成实机接线与 5 分钟稳定性验收；当前只实现 `camera_local.c/h` 的 QVGA JPEG 健康采帧，不传输图像。
- 没有 YOLO、ESP-DL 或真实端侧目标检测器。
- `distance_estimator` 目前是纯函数和测试，不是来自真实检测框的运行时测距链路。
- `voice_prompt` 只输出串口 `voice` JSON 事件，没有驱动真实语音模块。
- `airbag_control` 只输出 `actuator` 模拟事件，没有驱动真实气泵、电磁阀或泄气阀。
- 上位机 CSV 记录目前主要记录压力样本，不是完整多源事件日志。
- `motion` 在上位机有解析和占位显示，但固件侧没有 IMU/运动数据源。
- C 端 `vision_detect` 结构支持多个对象，但当前解析和最近类别选择仍以第一个对象为主。
- 真实摄像头、语音和泵阀仍未接入；Hardware 配置下无外部视觉输入时会保守输出 0%。

## 系统架构

### 当前代码架构

```text
ProjectFile/
├─ AIX/                 # ESP32-S3 ESP-IDF 固件工程
│  ├─ pressure_sensor   # GPIO1 / ADC1_CH0 气压采集
│  ├─ vision_input      # 接收 PC 光流 vision v1
│  ├─ vision_detect     # vision_detect 结构和字符串解析器
│  ├─ vision_detect_input
│  │                    # ESP 端模拟 truck 接近场景
│  ├─ camera_local      # OV5640 QVGA JPEG 采帧和状态恢复（Camera profile）
│  ├─ distance_estimator
│  │                    # 单目测距纯函数
│  ├─ risk_fusion       # v1 光流风险 + v2 vision_detect 风险
│  ├─ voice_prompt      # 串口 voice 事件
│  └─ airbag_control    # 串口 actuator 模拟事件
│
└─ host_app/            # Python / PySide6 上位机
   ├─ 串口收发 pressure / risk / actuator / vision_detect / voice
   ├─ PC/手机摄像头光流趋势分析并发送 vision v1
   ├─ 压力、风险、视觉检测、动作和事件流显示
   └─ 压力 CSV 记录
```

### 目标产品架构

```text
OV5640 / OV2640 摄像头
    -> camera_local
    -> yolo_detector 或 esp_dl_detector
    -> distance_estimator
    -> vision_detect
    -> risk_fusion + pressure_sensor
    -> voice_prompt
    -> airbag_control
    -> 真实气泵 / 电磁阀 / 气囊
```

目标架构还没有全部实现。当前仓库更准确的定位是“比赛演示和算法接口验证原型”。

## 模块状态

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| ESP32-S3 固件工程 | 已建立 | `AIX/`，ESP-IDF 工程，可构建 |
| XGZP6847A 气压采集 | 已实现 | `GPIO1 / ADC1_CH0`，含校准回退、滤波、有效性和过压判断 |
| `config` 调试协议 | 已实现 | 压力监测默认开启，可经隐藏 JSON 配置切换 |
| PC 外部 `vision` v1 | 已实现 | 上位机用 OpenCV 光流生成 `looming`、`area_rate`、`center_motion` |
| `vision_detect` 协议结构 | 已实现第一版 | 固件和上位机都有模型/解析；C 端暂以简单字符串扫描和首对象为主 |
| 模拟 `vision_detect` 输入 | 已实现 | ESP 端模拟 truck 从远到近，默认启动 |
| `distance_estimator` | 已实现纯函数 | 可用 GCC 测试，尚未接入真实相机检测框 |
| `risk_fusion` v1 | 已实现 | 处理 PC `vision` v1，作为 fallback |
| `risk_fusion` v2 | 已实现 | 处理 `vision_detect + pressure`，输出 category、nearest、TTC |
| `voice_prompt` | 已实现串口 stub | 输出 `voice` JSON，含基础 JSON 字符串转义 |
| `airbag_control` | 已实现模拟输出 | 输出 `actuator` JSON，没有真实 GPIO/PWM 控制 |
| 上位机 | 已实现第一版 | PySide6 界面、串口、压力曲线、视觉面板、事件流、压力 CSV |
| 自动化验证 | 已实现 | `scripts/verify.ps1` 运行 Python、编译检查和 8 组 C 测试；测试源码不再被忽略，可随下次提交纳入仓库 |
| OV5640 本地采帧 | 代码已实现，待实机验收 | Camera profile 固定 QVGA/JPEG、DRAM 单缓冲、状态上报和重试；不做检测 |
| 真实摄像头端侧检测 | 未实现 | 没有 YOLO/ESP-DL、bbox、测距或真实 `vision_detect` 输出 |
| 真实语音硬件 | 未实现 | 需要后续接语音模块、蜂鸣器或蓝牙音频 |
| 真实泵阀闭环 | 未实现 | 需要接 MOS、PWM、阀控、限压和急停策略 |
| 双目/雷达/IMU | 未实现 | 后续扩展，不是当前主线 |

## 串口事件

### pressure v1

ESP32-S3 输出：

```json
{"type":"pressure","version":1,"seq":123,"ts_ms":45678,"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,"over_pressure":false,"valid":true}
```

### vision v1

上位机发送给 ESP32-S3。当前来自 PC/手机摄像头光流趋势，不是真实目标检测。

```json
{"type":"vision","version":1,"seq":12,"ts_ms":43020,"source":"pc_camera","looming":0.72,"area_rate":0.58,"center_motion":0.41,"confidence":0.80,"valid":true}
```

### vision_detect v1

当前由 ESP32-S3 的模拟任务输出并写入本地 snapshot；上位机可以解析和显示。这里的 `source:"simulated"` 表示不是 OV5640 真实相机。

```json
{"type":"vision_detect","version":1,"seq":42,"ts_ms":50000,"source":"simulated","objects":[{"class":"truck","confidence":0.85,"bbox":[100,60,80,60],"distance_m":5.2,"approaching":true}],"nearest_distance_m":5.2,"ttc_s":4.1,"valid":true}
```

### camera_status v1

仅 Camera profile 输出；用于上位机显示 OV5640、分辨率、FPS、帧长度、失败次数和 PSRAM 状态，不包含 JPEG 内容，也不改变风险融合输入。

```json
{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg","frame_bytes":18432,"fps":5.00,"frames_ok":12,"capture_failures":0,"psram":false,"valid":true}
```

### risk v1 / risk v2

v1 是 PC 光流 fallback，v2 是 `vision_detect + pressure` 路径。

```json
{"type":"risk","version":1,"seq":35,"ts_ms":43100,"level":80,"target_pct":80,"reason":"vision_looming","vision_stale":false,"pressure_safe":true,"pressure_state":"safe"}
{"type":"risk","version":2,"seq":43,"ts_ms":50020,"level":40,"target_pct":40,"reason":"target_close","category":"vision_warning","nearest_class":"truck","nearest_distance_m":5.2,"ttc_s":4.1,"pressure_safe":true,"pressure_state":"safe"}
```

### voice v1 / actuator v1

二者当前都是串口模拟事件。

```json
{"type":"voice","version":1,"seq":43,"ts_ms":50030,"text":"注意，truck接近","played":true}
{"type":"actuator","version":1,"seq":43,"ts_ms":50030,"mode":"sim","target_pct":40,"pump":"inflate","valve":"closed"}
```

## 快速开始

### 固件

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\AIX
idf.py set-target esp32s3
idf.py build
idf.py flash monitor
```

Camera profile（关闭模拟 `vision_detect`）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -IdfProfile camera
```

当前压力传感器默认使用 ESP32-S3 `GPIO1 / ADC1_CH0`。需要在 ESP-IDF PowerShell 或 VSCode ESP-IDF 终端中运行 `idf.py`。

### 上位机

项目约定只使用这一套虚拟环境：

```text
D:\Projects\IOTCompetition\ProjectFile\.venv
```

安装或更新依赖：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd .\host_app
python -m pip install -r requirements.txt
```

运行上位机：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\run_host_app.cmd
```

未连接开发板时，可以勾选“模拟数据”检查压力界面和曲线；但模拟数据只模拟上位机压力样本，不会模拟完整固件事件链。

## 验证命令

上位机：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
..\.venv\Scripts\python.exe -m unittest discover -s tests -v
..\.venv\Scripts\python.exe -m compileall -q aix_host_app tests
```

固件纯函数和协议测试：

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

推荐统一使用仓库验证脚本；它会把 C 测试产物写入被忽略的 `.test-bin/`：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 下一步建议

1. 按 [`OV5640 接线说明`](docs/hardware/ov5640-devkitc1-wiring.md) 完成实机连续采帧验收，再接少类别轻量检测器。
2. 贯通 `detector -> distance_estimator -> vision_detect -> risk_fusion` 真实运行链路，并完善多目标“最近对象”语义。
3. 真实泵阀接入前，完成安全状态机、GPIO/PWM 抽象、过压停止、泄气和人工急停。
4. 上位机把 CSV 扩展为 pressure/vision/risk/voice/actuator/fault 多源事件日志。

## Git 上传约定

本仓库只上传源码、配置、文档和依赖清单。

不要上传：

- Python 虚拟环境：`.venv/`、`venv/`、`env/`
- Python 缓存：`__pycache__/`、`*.pyc`
- ESP-IDF 构建目录：`AIX/build/`
- 上位机日志和 CSV：`host_app/logs/`
- 本地工具缓存、串口日志和系统临时文件

## 安全边界

- 当前项目是风险提醒和比赛演示原型，不能包装成自动避撞系统。
- PC 上位机用于调试、演示和记录，不作为最终安全执行控制器。
- 当前 `vision_detect` 是模拟输入，不能代表真实道路视觉识别能力。
- `actuator` 只是模拟事件，不能代表真实气囊已经可安全充放气。
- 真实硬件接入前，必须验证过压、压力无效、摄像头无帧、检测置信度低、通信异常和人工急停等失效路径。
