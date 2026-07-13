# AIX 脉盔上位机

这是 ESP32-S3 的调试与状态监测上位机。它显示压力数据、OV5640 健康状态、PC DA3 相对深度结果、事件流、CSV 记录，并保留 motion 预留面板。

上位机不再提供本机摄像头、手机/IP 摄像头、画面预览、OpenCV 光流分析或视觉事件发送。OV5640 图像只在 ESP32-S3 本地处理。

## 当前职责

```text
串口读取 pressure / camera_status / vision_depth / motion
├─ pressure：压力曲线、状态与 CSV
├─ camera_status：OV5640 折叠状态卡和参数详情
├─ vision_depth：DA3-SMALL 相对深度、置信度与推理延迟
└─ motion：保留未来模块接口
```

视觉区域默认只显示可点击状态文字：

- `OV5640：等待状态`：未连接串口。
- `OV5640：状态正常`：3 秒内收到有效 `camera_status`。
- `OV5640：连接异常`：收到 `valid:false` 或连续 3 秒未收到状态。

点击状态文字可就地展开分辨率、格式、FPS、帧大小、成功帧、失败次数、PSRAM 和最后更新时间。

## 目录

```text
host_app/
├─ aix_host_app/
│  ├─ app.py             # 主窗口、串口路由、记录
│  ├─ models.py          # pressure / camera_status / motion
│  ├─ parsers.py         # 支持协议解析
│  └─ widgets/           # 压力、motion、OV5640 状态、事件流
├─ tests/
├─ requirements.txt
└─ run_host_app.cmd
```

## 运行

```powershell
cd D:\Projects\IOTCompetition\ProjectFile\host_app
.\run_host_app.cmd
```

项目统一使用 `D:\Projects\IOTCompetition\ProjectFile\.venv`。

## 验证

```powershell
cd D:\Projects\IOTCompetition\ProjectFile
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## 边界

- `camera_status` 表示相机健康；`vision_depth` 表示 PC 模型成功返回相对深度，二者缺一不可。
- `vision_depth` 不是米制距离，不直接控制风险或气囊。
- 当前风险和气囊卡片只是未来 UI 占位，不接收旧 risk/actuator 协议。
- `motion` 协议与面板保留，但当前固件没有运动数据源。
