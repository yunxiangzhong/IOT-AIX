# Depth Anything 3 + YOLO26m 本地运行目录

本目录是项目唯一的交通视觉运行根目录，源码、环境、模型、缓存和日志都留在这里：

```text
source/                官方 DA3 源码，固定提交
env/                   Python 3.10、CUDA PyTorch、DA3 与 Ultralytics
weights/DA3-SMALL/     相对深度模型
weights/YOLO26m/       yolo26m.pt 与本机导出的 yolo26m.engine
cache/                 Hugging Face、Torch、Ultralytics、Matplotlib 缓存
service/               FastAPI 推理服务与测试
logs/                  服务运行日志
```

执行 `powershell -ExecutionPolicy Bypass -File .\install.ps1` 会安装固定版本 `ultralytics==8.4.96`、下载官方 COCO `YOLO26m`，并优先在本机 RTX 4060 上导出 TensorRT FP16 引擎。若 TensorRT 导出不可用，服务只回退到 CUDA FP16 `.pt`，不会静默使用 CPU。实际文件、SHA256、Ultralytics 版本和后端写入 `install_manifest.json`。

服务组合 `DA3-SMALL`（280 像素处理分辨率）和 `YOLO26m`（512 像素），识别人、车、自行车、摩托车、公交车、卡车、交通灯和停止标志。512 仍高于 OV5640 当前 320×240 原始画面尺寸，是本机实测满足延迟余量的配置。启动后先完成两模型预热，预热前 `/healthz` 的 `model_ready` 为 `false`。

默认链路接口：

- `POST /v1/frames`：ESP32 上传最新 JPEG，HTTP 202 快速返回。
- `GET /v1/frame/latest.jpg`：最新上传原图，仅用于诊断。
- `GET /v1/frame/processed.jpg`：最新已完成分析的画面，上位机默认使用此接口。
- `GET /v1/state/latest`：同一 `frame_seq` 的检测框、稳定风险和动作确认。
- `GET /v1/semantic/{analysis_id}/keyframes/{1|2|3}.jpg`：读取服务缓存的实际网关输入帧；标识和索引均严格校验。
- `POST /v1/collision-indicator/ack`：用最近真实设备地址代理匹配 boot/count 的白色模拟 Airbag 确认。
- `POST /v1/road-hazards`：接收路侧协同预警事件，立即返回 202；仅向最近 3 秒内有上传画面的同设备地址异步下发，并在 `state/latest` 的 `road_hazard` 中记录采集、识别、到达预测、下发和 ACK 五阶段。该演示链路只接受受控枚举与严格匹配的设备 ACK，不代表已完成实车验证。
- `GET /healthz`：HTTP、模型、GPU 与后端状态。

风险采用交通目标优先、非对称 EMA、两帧升级和三帧降级；场景深度本身最多到“注意”。它表示相对视觉接近程度，不是碰撞概率或安全控制结论。

边缘语义支路从环境变量 `VEI_API_KEY` 读取火山引擎边缘网关密钥，固定调用
`doubao-seed-1.6-flash`。启动脚本仅在当前进程没有该变量时读取仓库根目录下被忽略的
`.env.local`；可复制 `.env.local.example`，但不得提交真实密钥。语义输出只包含场景、
道路环境、交通流、视野、跨帧变化、可信度和不确定性；响应中出现风险或执行字段会被拒绝。

许可边界：Ultralytics 软件及默认模型采用 `AGPL-3.0-or-later`，商业闭源分发需自行评估并可能需要 Ultralytics Enterprise License。本仓库的部署不改变该许可条件。
