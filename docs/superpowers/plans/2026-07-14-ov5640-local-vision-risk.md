# OV5640 本地视觉识别、风险同步与会话存储实施计划

**目标：** 上位机拉取 OV5640 JPEG，在 PC 本地运行 DA3-SMALL + TorchVision SSDLite，生成并显示 0–100 相对视觉风险，同时保存完整会话数据并通过 HTTP 回传 ESP32-S3。

**边界：** 第一版风险只用于显示、记录和 ESP 数据同步，不驱动气囊或其他执行器；本轮不连接、不烧录 ESP32-S3。

## 执行任务

- [ ] 扩展 `Models/DepthAnything3/service`，新增 SSDLite、风险算法和 `POST /v1/analyze`，保留旧 `/v1/infer`。
- [ ] 在 `host_app/aix_host_app` 中拆出视觉流水线、模型服务管理和会话记录，加入目录选择、自动建会话、风险卡和标注切换。
- [ ] 在 `AIX/main` 增加 JPEG 帧元数据响应头、`POST /risk` 接收与 `risk_ack`，补充主机侧 C 测试。
- [ ] 更新 README、权重安装脚本和验证脚本；运行 Python/C 测试与 ESP-IDF 编译，不执行 flash。

## 固定默认值

- 数据根目录：`F:\\OV5640`；会话目录：`YYYYMMDD_HHMMSS`。
- 预览约 2.5 FPS；模型处理最新帧，最多 1 FPS，不积压请求。
- 风险：DA3 前方 ROI 兜底 + SSDLite 相关目标风险，0–100，均衡上升/下降平滑系数 0.65/0.25。
- 模型服务：`127.0.0.1:8008`；ESP 预览和风险接口：端口 `8080`。
