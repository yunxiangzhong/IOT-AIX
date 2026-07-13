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

启动服务：`powershell -ExecutionPolicy Bypass -File .\run_service.ps1`。服务监听 `0.0.0.0:8008`，提供 `GET /healthz` 与 `POST /v1/infer`；请求体为 JPEG，必须携带 `X-Frame-Seq` 和 `X-Capture-Ts-Ms`。

默认模型是 `DA3-SMALL`，输出为相对深度统计，不能视为米制距离或安全控制结论。PC 视觉服务还使用 TorchVision `SSDLite320-MobileNetV3` COCO 权重生成轻量目标检测结果和相对风险；首次安装会把检测权重放到 `weights/SSDLite320-MobileNetV3/`。

`POST /v1/analyze` 是上位机使用的联合分析接口，返回深度、检测框和 `0–100` 相对视觉风险。风险用于显示、记录和同步，不驱动执行器。后续可升级到相机标定、DA3Metric、TTC/跟踪、骑行数据集微调和离线参数标定。
