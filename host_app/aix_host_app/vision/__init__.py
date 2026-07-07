from .analysis import NullVisionAnalyzer, VisionAnalysisResult, VisionFeatureEvent, VisionTrendAnalyzer
from .bridge import VisionEventBridge
from .camera import CameraFrame, CameraSourceConfig

__all__ = [
    "CameraFrame",
    "CameraReader",
    "CameraSourceConfig",
    "NullVisionAnalyzer",
    "VisionAnalysisResult",
    "VisionEventBridge",
    "VisionFeatureEvent",
    "VisionTrendAnalyzer",
]


def __getattr__(name: str):
    if name == "CameraReader":
        from .reader import CameraReader

        return CameraReader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
