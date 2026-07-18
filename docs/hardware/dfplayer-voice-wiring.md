# DFPlayer Mini 视觉风险语音接线与验收

本说明只为当前视觉风险链路增加语音提示：PC 推理服务在已通过 token、设备、boot_id、帧序和 TTL 校验的 `/risk` 回调中携带 `voice_prompt`；ESP32-S3 再通过 UART2 控制 DFPlayer Mini。它不接入 MPU6050、气动控制、故障播报或实时 TTS，且不是安全保障或紧急告警设备。

## 接线

在 ESP32-S3-DevKitC-1 断电状态下完成下表接线。DFPlayer 与 ESP 必须共地。

| DFPlayer Mini 引脚 | 连接 | 说明 |
| --- | --- | --- |
| VCC | 开发板 5V | 默认从开发板 5V 供电；必须确认模块端实际电压为 3.3–5.0V。 |
| GND | 开发板 GND | UART、音频与供电共地。 |
| RX | ESP32-S3 GPIO47（TX）串联 1 kΩ 电阻 | 电阻靠近 DFPlayer RX 一侧即可；不要把 GPIO47 直接短接到模块 RX。 |
| TX | ESP32-S3 GPIO48（RX） | 使用模块 UART TX；若实测 TX 高电平超过 ESP32-S3 可接受的 3.3V，先加分压或电平转换，禁止直接接入。 |
| SPK1 / SPK2 | 8 Ω、3 W 喇叭两端 | 喇叭只能跨接 SPK1 与 SPK2；任一端都不得接 GND。 |

GPIO47/48 是该固件专用 UART2：9600、8N1。不要把它们与 OV5640、GPIO38 RGB、GPIO40/41 气动或 USB-UART 复用。

DFPlayer 播放时可能有瞬态电流。若出现 brownout、ESP 重启、相机掉线、USB 断连、明显杂音，或 DFPlayer 端电压不在 3.3–5.0V 范围内，停止从开发板取电，改用独立、稳定的 5V（建议至少 1 A）给 DFPlayer，并保留与 ESP32-S3 的 GND 共地。不要用 ESP 的 3.3V 引脚给该模块或喇叭供电。

## TF 卡与音频文件

1. 使用不大于 32 GB 的 TF/microSD 卡，格式化为 FAT32。
2. 在卡根目录新建小写目录 `mp3`，放入以下文件：

   ~~~text
   /mp3/0001.mp3  注意前方环境
   /mp3/0002.mp3  前方风险较高，请减速避让
   /mp3/0003.mp3  前方危险，请立即减速避让
   ~~~

3. 每个文件开头保留至少 500 ms 静音，避免 DFPlayer 启动时吞掉第一字。
4. 文件名必须是四位数字；不要依赖 FAT 文件写入顺序或改成 `1.mp3`、`01.mp3`。

固件用 DFPlayer `0x12` 指令按 `/mp3/0001.mp3` 到 `/mp3/0003.mp3` 精确播放，默认音量为 `18/30`。

## 上电与故障排查

- 串口首先应出现 `voice_status` 的 `initializing`；检测到 TF 卡并设置 SD 源和音量后为 `ready`。播放期间为 `playing`，曲目结束为 `finished`；无法检测 TF 卡、UART 写入失败或模块上报错误时为 `error`。
- `action_ack.voice_ack` 的 `queued` 表示已入队，`duplicate` 表示 HTTP 重试被幂等确认且不再播放，`suppressed` 表示更高风险语音仍在播放，`unavailable` 表示 DFPlayer/TF 尚未可用，`rejected` 表示语音字段不合法。
- 完全无声时，依次检查 TF 是否 FAT32、`/mp3/0001.mp3` 拼写、SPK1/SPK2 是否接到了同一只 8 Ω 喇叭、GPIO47 是否经过 1 kΩ 接到 RX、GND 是否共地。
- 只有 `low`、过期帧、乱序帧、错误曲目和未通过 `/risk` 原有校验的请求不会触发播放；这不是模块故障。

## 验收顺序

1. 断开喇叭，确认 VCC/GND/UART 接线后上电；串口应持续输出非阻塞状态，不影响相机和 Wi-Fi。
2. 插入准备好的 TF 卡，确认 `voice_status.ready`；再接入喇叭。
3. 从 PC 发送 attention/high/critical 风险，确认分别仅播放 0001/0002/0003；low、过期帧、乱序帧和错误曲目均不播放。
4. 连续 12 秒同级风险最多听到两次；播放低风险期间触发 critical，应立即切换到 0003。
5. 完整运行相机、Wi-Fi、推理与语音链路 10 分钟，确认没有 brownout、相机掉线、USB 断连或明显杂音。

完成以上步骤仅表示该原型的实机功能通过，不能证明其具备人身安全、医疗、碰撞预警或认证级可靠性。
