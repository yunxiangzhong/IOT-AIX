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
- `GET /healthz`：HTTP、模型、GPU 与后端状态。

风险采用交通目标优先、非对称 EMA、两帧升级和三帧降级；场景深度本身最多到“注意”。它表示相对视觉接近程度，不是碰撞概率或安全控制结论。

许可边界：Ultralytics 软件及默认模型采用 `AGPL-3.0-or-later`，商业闭源分发需自行评估并可能需要 Ultralytics Enterprise License。本仓库的部署不改变该许可条件。
