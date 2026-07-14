# AIX 主动视觉闭环设计说明

## 单一默认链路

```text
OV5640 → ESP JPEG 上传 → PC LatestFrameStore → AnalysisWorker
       → vision_risk callback → ESP action_policy → GPIO38 RGB
       → action_ack / action_status → chain_state / PySide6
```

关键不变量：

1. 上传 HTTP 与模型加载解耦；模型冷启动期间仍返回 202 并保存最新帧。
2. 每个 `device_id + boot_id` 最多一个待分析帧；推理中的新帧覆盖旧待处理帧。
3. 回调地址只取上传连接的源 IP，固定端口 8080。
4. ESP 是动作策略唯一执行者；PC 和 UI 不能用 HTTP 200 冒充动作确认。
5. 风险 3 秒失效，启动 45 秒宽限；错误 boot、重复、乱序、过期和等级不一致均不改变 RGB 风险状态。

## 协议

上传：`POST /v1/frames`，JPEG 不超过 256 KiB，携带 `X-AIX-Token`、`X-Device-Id`、`X-Boot-Id`、`X-Frame-Seq`、`X-Capture-Ts-Ms`，返回 HTTP 202 `frame_ack`。

回调：`POST http://<ESP-IP>:8080/risk`，正文 `vision_risk v1`；成功返回同帧 `action_ack v1`，包括 `action_state` 与 `rgb_pattern`。

上位机：轮询 PC `/v1/state/latest`；只在 `boot_id + frame_seq` 变化时读取 `/v1/frame/latest.jpg`。串口 `action_status` 用于独立确认实际动作状态。

## 故障模型

- 相机无效、Wi-Fi/HTTP 失败、模型错误、风险超时：紫色 1 Hz。
- 模型加载：蓝色 1 Hz。
- 新鲜 low/attention/high/critical：绿常亮/黄 1 Hz/橙 2 Hz/红双脉冲。
- 回调失败重试当前最新结果，间隔 200/500/1000 ms；若被新上传帧替代，旧结果停止重试。

## 验收门槛

自动化验证必须全绿并完成 ESP-IDF 全量构建。最终还需目标板连续运行 10 分钟：采集约 5 FPS、上传约 2.5 FPS、接受率至少 95%、有效结果至少 250 个、每个实际回调获得同帧动作确认、回调 P95 小于 500 ms，并完成停模、断网、旧帧和错误 token 的恢复测试。

该设计只产生相对视觉风险和板载 RGB 原型提示，不构成碰撞概率或安全控制认证。
