from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraSourceConfig:
    kind: str
    value: str
    width: int = 640
    height: int = 360
    fps: int = 15

    def __post_init__(self) -> None:
        if self.kind not in {"local", "url"}:
            raise ValueError("摄像头来源类型必须是 local 或 url")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("摄像头分辨率必须为正数")
        if self.fps <= 0:
            raise ValueError("摄像头帧率必须为正数")

    def capture_input(self) -> int | str:
        value = self.value.strip()
        if self.kind == "url":
            if not value:
                raise ValueError("网络摄像头地址不能为空")
            return value

        try:
            index = int(value)
        except ValueError as exc:
            raise ValueError("本机摄像头编号必须是整数，例如 0") from exc
        if index < 0:
            raise ValueError("本机摄像头编号不能为负数")
        return index

    def source_label(self) -> str:
        if self.kind == "local":
            return f"本机摄像头 {self.capture_input()}"
        return str(self.capture_input())


@dataclass(frozen=True)
class CameraFrame:
    frame_id: int
    ts_ms: int
    width: int
    height: int
    source: str
    rgb_data: bytes
    bytes_per_line: int
