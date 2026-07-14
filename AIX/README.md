# AIX ESP32-S3 主动视觉固件

目标板为 ESP32-S3-DevKitC-1 v1.1，OV5640 固定为 320×240 JPEG、约 5 FPS；板载 WS2812 兼容 RGB 位于 GPIO38。

## 任务装配

```text
app_main
├─ device_identity             每次启动生成 64 位 boot_id
├─ action_controller           45 s 宽限、3 s TTL、action_status 心跳
│  └─ rgb_status               led_strip RMT / GPIO38 / 最大亮度 20%
├─ network_runtime             NVS、事件循环、STA 只初始化一次
├─ risk_receiver :8080/risk    token / device / boot / seq / band 校验
├─ vision_uplink               每 400 ms 复制最新 JPEG → PC /v1/frames
├─ camera_local                OV5640 采集、状态和失败恢复
└─ pressure_sensor             GPIO1 / ADC1_CH0 压力遥测
```

`camera_preview` 只作为显式开启的诊断兼容模块保留，默认关闭，端口 8081；`/risk` 已从该模块拆出，不与预览生命周期耦合。

## 运行时配置

```powershell
.\sync_runtime_config.ps1
```

脚本创建被 Git 忽略的 `sdkconfig.runtime`，首次优先迁移现有 `sdkconfig.preview` 的 Wi-Fi 凭据，不删除旧文件，并补齐：

- `CONFIG_AIX_DEVICE_ID="aix-helmet-01"`
- `CONFIG_AIX_LINK_TOKEN="<本机随机 256 位 token>"`
- `CONFIG_AIX_VISION_SERVICE_URL="http://192.168.137.1:8008/v1/frames"`
- 主动上传 400 ms、风险接收 8080、预览关闭、RGB 开启。

## 风险校验与动作

`risk_receiver` 仅接受 `vision_risk v1`，并拒绝：错误 token、错误 device_id/boot_id、重复或乱序帧、未来时间戳、超过 3 秒的结果、无效分数以及分数/等级不一致。

成功响应必须是同帧 `action_ack`；串口在动作状态变化时立即输出 `action_status`，并每秒心跳一次。HTTP 200 本身不等于动作确认。

## 构建

推荐使用项目统一验证，避免 Windows 子进程 PATH 丢失：

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -BuildFirmware
```

固件使用自定义 2 MiB 单应用分区布局，避免新增 HTTP/RGB 组件后挤占默认 1 MiB factory 分区。生成物位于 `AIX/build-verify/`，其中 `firmware-manifest.json` 可用于烧录追溯。

手动烧录前确认串口：

```powershell
idf.py -p COMxx flash monitor
```

## 硬件边界

- 已使用：OV5640、XGZP6847A、板载 GPIO38 RGB。
- 未接入：蜂鸣器、振动马达、气泵、电磁阀、气囊。
- RGB 是原型语义提示，不是安全执行器。
- 接线见 [OV5640 DevKitC-1 接线说明](../docs/hardware/ov5640-devkitc1-wiring.md)。
