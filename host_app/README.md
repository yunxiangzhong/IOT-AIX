# AIX 工业仪表上位机

PySide6 上位机只消费 PC 主动帧服务，不再拉取 ESP `/capture.jpg`，也不再从 UI 提交同步模型推理或向 ESP 发送风险。

## 默认展示页

- 顶部：设备、热点、模型与展示/诊断/设置入口。
- 四段链路：OV5640 采集 → ESP 上传 → PC 推理 → ESP 动作确认。
- 主区：70% 最新帧、30% 风险与 GPIO38 动作。
- 底部：上传 FPS、帧年龄、推理/回调延迟、确认帧和最后错误。
- 诊断抽屉：链路、协议、设备、会话四页。

速度、加速度和气囊不出现在默认页；诊断设备页明确标记为“未接入”。串口、波特率、存储目录和模拟开关位于设置弹窗。

## 数据源

- PC HTTP：`/healthz`、`/v1/frame/latest.jpg`、`/v1/state/latest`。
- ESP 串口：`pressure`、`camera_status`、`action_status`；旧 `camera_preview`/`vision_depth` 即使出现也不会改变默认 PC 帧源。

## 会话

首次收到链路或串口数据后自动创建会话，按帧号去重保存：

```text
frames/
vision.ndjson
telemetry.ndjson
action.ndjson
pressure.csv
model.log
session.json
```

模型服务 stdout/stderr 由统一启动器写入 `host_app/logs/`，上位机按增量同步到当前会话 `model.log`。

## 启动

```powershell
.\start_host_app.cmd
```

这是唯一推荐入口，会依次同步运行时配置、检查 2.4 GHz 热点、启动异步模型服务、检查 HTTP 健康并启动 UI。旧 `run_host_app.cmd` 不作为链路入口。

## 设计与验证

高保真 HTML 原型位于 [aix-host-dashboard-prototype.html](../docs/design/aix-host-dashboard-prototype.html)，使用真实 OV5640 样例帧。界面采用暖灰 `#F4F3EF`、工作面 `#FCFBF7`、石墨文字 `#20201E`，状态色只表达语义，无装饰渐变或玻璃效果。

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

当前视觉结果是相对风险，板载 RGB 仅是原型提示，不应解释为碰撞概率或安全执行器动作。
