# Depth Anything 3 本地运行目录

本目录是项目唯一的 DA3 本地安装根目录：

```text
source/     官方源码，固定提交 41736238f5bced4debf3f2a12375d2466874866d
env/        Python 3.10、CUDA PyTorch、官方 DA3 依赖
weights/    DA3-SMALL 本地权重
cache/      Hugging Face 与 Torch 缓存
service/    FastAPI 推理服务与测试
logs/       服务运行日志
```

安装或修复环境：`powershell -ExecutionPolicy Bypass -File .\install.ps1`。

推荐通过 `host_app/start_host_app.cmd` 启动完整链路。服务监听 `0.0.0.0:8008`，进程先开放 HTTP，再在后台加载 DA3 与 SSDLite；冷启动期间 `POST /v1/frames` 仍会立即接收并覆盖缓存最新 JPEG。

默认模型是 `DA3-SMALL`，输出为相对深度统计，不能视为米制距离或安全控制结论。PC 视觉服务还使用 TorchVision `SSDLite320-MobileNetV3` COCO 权重生成轻量目标检测结果和相对风险；首次安装会把检测权重放到 `weights/SSDLite320-MobileNetV3/`。

默认接口为 `POST /v1/frames`、`GET /v1/frame/latest.jpg`、`GET /v1/state/latest` 和 `GET /healthz`。单 GPU worker 只分析最新待处理帧，并把 `vision_risk` 回调 ESP；旧 `/v1/infer`、`/v1/analyze` 只为兼容保留。风险只用于原型 RGB 提示，不是碰撞概率。
