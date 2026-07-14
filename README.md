# AIX 主动视觉头盔原型

本工程实现一条可确认动作结果的主动视觉闭环：

```text
OV5640 → ESP32-S3 主动上传 JPEG → PC 最新帧缓存 / DA3 + SSDLite 推理
        → PC 回调 vision_risk → ESP action_policy → GPIO38 板载 RGB
        → action_ack + 串口 action_status → PySide6 上位机
```

ESP32-S3 约 5 FPS 采集 QVGA JPEG、每 400 ms 复制最新帧上传；PC 对上传立即返回 HTTP 202，GPU 只分析每个启动周期的最新待处理帧，不形成积压。风险结果 3 秒失效，启动宽限 45 秒。

## 当前实现

| 模块 | 状态 |
| --- | --- |
| OV5640 QVGA/JPEG 采集与失败恢复 | 已实现 |
| `POST /v1/frames` 主动上传、token 和 256 KiB 限制 | 已实现并自动化测试 |
| 模型后台加载、最新帧覆盖、单 GPU worker | 已实现并自动化测试 |
| PC → ESP `/risk` 回调与 200/500/1000 ms 重试 | 已实现并自动化测试 |
| boot_id、帧序、3 秒 TTL、风险分段校验 | 已实现并主机侧 C 测试 |
| GPIO38 RGB 六种语义模式与 `action_status` | 已实现并通过 ESP-IDF 全量构建 |
| PySide6 工业仪表 UI 与诊断抽屉 | 已实现并在 1920×1080、1280×720 验证 |
| 10 分钟实机闭环及断网/停模恢复 | 需连接目标板后执行最终验收 |

## 单一启动入口

双击或运行：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\start_host_app.cmd
```

启动器依次执行：

1. 从旧 `AIX/sdkconfig.preview` 首次迁移并同步被 Git 忽略的 `AIX/sdkconfig.runtime`；旧文件不会删除。
2. 配置并核验 Windows 2.4 GHz 移动热点。
3. 启动 `0.0.0.0:8008` 异步模型服务并保存 stdout/stderr。
4. 等待 `/healthz` 的 HTTP 层就绪（模型可以仍在后台加载）。
5. 启动 PySide6 上位机；退出 UI 时停止本次模型服务。

首次变更热点凭据或 token 后，需要重新构建并烧录固件。运行时配置和 token 不提交 Git。

## PC 服务接口

- `POST /v1/frames`：ESP 上传 JPEG，成功返回 `frame_ack`（HTTP 202）。
- `GET /healthz`：HTTP、模型加载、GPU 和错误状态。
- `GET /v1/frame/latest.jpg?device_id=aix-helmet-01`：上位机读取最新上传帧。
- `GET /v1/state/latest?device_id=aix-helmet-01`：上传、模型、风险、回调和 RGB 确认的统一 `chain_state`。
- PC 使用上传请求源 IP 回调 `POST http://<ESP-IP>:8080/risk`，避免客户端注入回调地址。

旧 `/v1/infer` 和 `/v1/analyze` 仅为兼容测试保留，不是默认链路。上位机不再拉取 ESP `/capture.jpg`、不再提交本地同步推理、也不代替 ESP 执行动作策略。

## RGB 语义

| 状态 | GPIO38 板载 RGB（最大 20%） |
| --- | --- |
| 启动 / 模型加载 | 蓝色 1 Hz |
| low 0–29 | 绿色常亮 |
| attention 30–59 | 黄色 1 Hz |
| high 60–79 | 橙色 2 Hz |
| critical 80–100 | 红色双脉冲 |
| 超时、相机、网络或模型错误 | 紫色 1 Hz |

不接入蜂鸣器、振动、气泵、电磁阀或气囊。

## 验证与构建

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BuildFirmware
```

`-BuildFirmware` 会自动进入 ESP-IDF 环境、在子进程内验证 CMake/Ninja/交叉编译器、关闭 ccache、全量构建并生成 `AIX/build-verify/firmware-manifest.json`。清单记录 Git commit/dirty 状态、sdkconfig SHA-256、AIX.bin SHA-256 和大小，不包含 token。

## 数据与安全边界

会话按帧号去重保存 `frames/`、`vision.ndjson`、`telemetry.ndjson`、`action.ndjson`、`pressure.csv`、`model.log` 和 `session.json`。

当前模型输出是相对视觉风险，不是米制距离、碰撞概率或安全执行器结论；板载 RGB 只用于原型提示。没有完成 10 分钟实机验收前，不应把本系统描述为自动避撞或安全控制产品。

详细设计见 [主动视觉闭环说明](docs/design/active-vision-closed-loop.md)，固件见 [AIX README](AIX/README.md)，上位机见 [host_app README](host_app/README.md)。
