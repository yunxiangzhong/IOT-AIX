from __future__ import annotations

import uuid

from PySide6 import QtCore, QtGui, QtWidgets


_COLORS = {"waiting": "#86868B", "active": "#007AFF", "completed": "#248A3D", "failed": "#D70015"}

SCENARIOS = {
    4: {
        "title": "货车盲区",
        "subtitle": "右侧盲区有来车，请减速注意避让",
        "map_title": "十字路口 · 右侧盲区",
        "target": "货车",
        "track": 4,
        "severity": "high",
    },
    5: {
        "title": "儿童横穿",
        "subtitle": "右前方盲区有儿童横穿，请立即减速，注意避让",
        "map_title": "直道 · 右前方盲区",
        "target": "儿童",
        "track": 5,
        "severity": "critical",
    },
    6: {
        "title": "施工绕行",
        "subtitle": "前方施工围挡后有行人进入车道，请立即减速，注意绕行",
        "map_title": "前方施工区域",
        "target": "行人",
        "track": 6,
        "severity": "critical",
    },
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _segment_intersects_rect(start: tuple[float, float], end: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    """Liang-Barsky segment test used by geometry regression tests and drawing annotations."""
    x0, y0 = start
    x1, y1 = end
    left, top, width, height = rect
    right, bottom = left + width, top + height
    dx, dy = x1 - x0, y1 - y0
    p_values = (-dx, dx, -dy, dy)
    q_values = (x0 - left, right - x0, y0 - top, bottom - y0)
    u1, u2 = 0.0, 1.0
    for p_value, q_value in zip(p_values, q_values):
        if abs(p_value) < 1e-9:
            if q_value < 0:
                return False
            continue
        ratio = q_value / p_value
        if p_value < 0:
            u1 = max(u1, ratio)
        else:
            u2 = min(u2, ratio)
        if u1 > u2:
            return False
    return True


def scene_geometry(
    scene_id: int,
    width: int,
    height: int,
    *,
    progress: float = 0.0,
    rider_progress: float = 0.0,
) -> dict:
    """Return normalized road geometry for visual rendering and invariant tests."""
    width = max(1, int(width))
    height = max(1, int(height))
    road_left = width * 0.27
    road_top = height * 0.03
    road_width = width * 0.50
    road_height = height * 0.93
    road = (road_left, road_top, road_width, road_height)
    center_x = road_left + road_width * 0.5
    rider = (road_left + road_width * 0.75,
             road_top + road_height * 0.91 - _clamp01(rider_progress) * road_height * 0.56)

    if scene_id == 5:
        cross_y = road_top + road_height * 0.24
        # The parked vehicle is aligned with the lane (long axis along the road),
        # so its body is visibly vertical in the top-down view rather than a
        # horizontal cross-road rectangle.
        van = (road_left + road_width * 0.64, cross_y - road_height * 0.065,
               road_width * 0.19, road_height * 0.25)
        child_progress = _clamp01((progress - 0.12) / 0.72)
        child = (van[0] + van[2] * 0.50 - child_progress * road_width * 0.36,
                 van[1] + van[3] * 0.20 + child_progress * road_height * 0.06)
        return {
            "road": road,
            "rider": rider,
            "target": child,
            "vehicle": van,
            "rider_in_road": road_left < rider[0] < road_left + road_width and road_top < rider[1] < road_top + road_height,
            "rider_in_open_lane": True,
            "line_blocked_by_vehicle": _segment_intersects_rect(rider, child, van),
            "line_blocked_by_fence": False,
            "construction_in_opposite_lane": False,
            "cross_y": cross_y,
        }

    if scene_id == 6:
        construction = (road_left, road_top + road_height * 0.13,
                        road_width * 0.47, road_height * 0.58)
        fence = (center_x - width * 0.012, construction[1], width * 0.024, construction[3])
        pedestrian_progress = _clamp01((progress - 0.16) / 0.68)
        pedestrian = (construction[0] + construction[2] * 0.62 + pedestrian_progress * road_width * 0.28,
                      construction[1] + construction[3] * 0.38 + pedestrian_progress * road_height * 0.08)
        return {
            "road": road,
            "rider": rider,
            "target": pedestrian,
            "construction": construction,
            "fence": fence,
            "rider_in_road": road_left < rider[0] < road_left + road_width and road_top < rider[1] < road_top + road_height,
            "rider_in_open_lane": center_x < rider[0] < road_left + road_width,
            "line_blocked_by_vehicle": False,
            "line_blocked_by_fence": _segment_intersects_rect(rider, pedestrian, fence),
            "construction_in_opposite_lane": construction[0] >= road_left and construction[0] + construction[2] <= center_x + width * 0.01,
            "cross_y": road_top + road_height * 0.24,
        }

    return {"road": road, "rider": rider, "target": (center_x, road_top + road_height * 0.2),
            "rider_in_road": True, "rider_in_open_lane": True,
            "line_blocked_by_vehicle": False, "line_blocked_by_fence": False,
            "construction_in_opposite_lane": False, "cross_y": road_top + road_height * 0.24}


class _ScenarioMap(QtWidgets.QWidget):
    def __init__(self, scene_id: int = 4, parent=None) -> None:
        super().__init__(parent)
        self.scene_id = scene_id
        self.progress = 0.0
        self.eta_seconds = 5.0
        self.phase = "等待演示"
        self.reduced_motion = False
        self.rider_lane = "northbound_right"
        self.rider_progress = 0.0
        self.rider_slowed = False
        self.rider_speed_kmh = 18
        self.setMinimumSize(560, 380)
        cfg = SCENARIOS.get(scene_id, SCENARIOS[4])
        self.setAccessibleName(f"{cfg['map_title']}协同预警模拟")

    def set_state(
        self, progress: float, eta_seconds: float, phase: str, *,
        rider_progress: float = 0.0, rider_slowed: bool = False, rider_speed_kmh: int = 18,
    ) -> None:
        progress = max(0.0, min(1.0, progress))
        if self.reduced_motion:
            progress = round(progress * 5) / 5
        self.progress = progress
        self.eta_seconds = max(0.0, eta_seconds)
        self.phase = phase
        self.rider_progress = max(0.0, min(1.0, rider_progress))
        self.rider_slowed = rider_slowed
        self.rider_speed_kmh = rider_speed_kmh
        cfg = SCENARIOS.get(self.scene_id, SCENARIOS[4])
        self.setAccessibleDescription(f"{cfg['target']}预计到达约 {self.eta_seconds:.1f} 秒，当前阶段：{phase}")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(bounds, QtGui.QColor("#E7EFE7"))

        if self.scene_id == 4:
            self._draw_scene_004(painter, bounds)
        elif self.scene_id == 5:
            self._draw_scene_005(painter, bounds)
        elif self.scene_id == 6:
            self._draw_scene_006(painter, bounds)

        # Common phase text bottom-left
        cfg = SCENARIOS.get(self.scene_id, SCENARIOS[4])
        painter.setPen(QtGui.QColor("#6E6E73"))
        painter.drawText(bounds.adjusted(14, 12, -14, -12),
                         QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
                         f"{cfg['map_title']}\n{self.phase}")

    def _draw_scene_004(self, painter, bounds) -> None:
        """L-crossroad with truck approaching from right, rider from below, building blocks view."""
        road = QtGui.QColor("#60646C")
        lane = QtGui.QColor("#D8D8DC")
        # Anchor the L-shaped intersection toward the upper-left so both relevant
        # approaches use the available canvas instead of leaving a large dead area.
        cx = int(bounds.left() + bounds.width() * 0.30)
        cy = int(bounds.top() + bounds.height() * 0.28)
        road_w = max(150, int(min(bounds.width(), bounds.height()) * 0.34))
        # The map intentionally contains only the two approaches relevant to this event:
        # truck from the right, rider from below. The unused upper/left arms are omitted.
        junction = QtCore.QRect(cx - road_w // 2, cy - road_w // 2, road_w, road_w)
        horizontal = QtCore.QRect(cx, cy - road_w // 2, bounds.right() - cx, road_w)
        vertical = QtCore.QRect(cx - road_w // 2, cy, road_w, bounds.bottom() - cy)
        painter.fillRect(junction, road)
        painter.fillRect(horizontal, road)
        painter.fillRect(vertical, road)

        dash_pen = QtGui.QPen(lane, 2, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(dash_pen)
        painter.drawLine(cx, cy, bounds.right(), cy)
        painter.drawLine(cx, cy, cx, bounds.bottom())

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#F5F5F7"))
        stripe = 8
        for offset in range(-road_w // 2 + 10, road_w // 2 - 8, 18):
            painter.drawRect(cx + offset, cy + road_w // 2 + 4, stripe, 18)
            painter.drawRect(cx + road_w // 2 + 4, cy + offset, 18, stripe)

        # South-east building blocks the rider's view of traffic approaching from the right.
        building = QtCore.QRect(cx + road_w // 2 + 18, cy + road_w // 2 + 18,
                                max(80, bounds.right() - (cx + road_w // 2 + 28)),
                                max(80, bounds.bottom() - (cy + road_w // 2 + 28)))
        painter.setBrush(QtGui.QColor("#D4C8B6"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#A89984"), 2))
        painter.drawRoundedRect(building, 10, 10)
        painter.setPen(QtGui.QColor("#5C5144"))
        painter.drawText(building.adjusted(8, 8, -8, -8), QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft, "街角建筑\n遮挡视线")

        # The rider travels north in the right-hand lane (China right-side traffic).
        rider_start_y = bounds.bottom() - 44
        # A longer lower approach makes the rider movement readable before the stop line.
        rider_stop_y = cy + road_w * 0.64 + 30
        rider_y = rider_start_y + (rider_stop_y - rider_start_y) * self.rider_progress
        rider = QtCore.QPointF(cx + road_w * 0.19, rider_y)
        truck_start = bounds.right() - 58
        # ETA=0 means the truck nose has just reached the intersection stop line, never passed it.
        truck_end = cx + road_w * 0.66
        truck_x = truck_start + (truck_end - truck_start) * self.progress
        truck_center = QtCore.QPointF(truck_x, cy - road_w * 0.20)

        blind = QtGui.QPolygonF([rider, QtCore.QPointF(building.left(), building.bottom()), truck_center])
        blind_color = QtGui.QColor("#FF9F0A")
        blind_color.setAlpha(48)
        painter.setBrush(blind_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#C93400"), 2, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(blind)

        # Roadside camera and field of view.
        camera_pos = QtCore.QPointF(bounds.right() - 34, cy - road_w // 2 - 42)
        fov = QtGui.QPolygonF([camera_pos, QtCore.QPointF(cx + 20, cy - road_w // 2), QtCore.QPointF(bounds.right() - 15, cy + road_w // 2)])
        fov_color = QtGui.QColor("#007AFF")
        fov_color.setAlpha(32)
        painter.setBrush(fov_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#007AFF"), 1, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(fov)
        painter.setBrush(QtGui.QColor("#1D1D1F"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QtCore.QRectF(camera_pos.x() - 13, camera_pos.y() - 8, 26, 16), 4, 4)
        painter.setPen(QtGui.QColor("#1D1D1F"))
        painter.drawText(int(camera_pos.x() - 118), int(camera_pos.y() - 22), 110, 20,
                         QtCore.Qt.AlignmentFlag.AlignRight, "路侧摄像头")

        # Truck body and detection box.
        truck = QtCore.QRectF(truck_center.x() - 34, truck_center.y() - 18, 68, 36)
        painter.setBrush(QtGui.QColor("#FF9F0A"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#9C4A00"), 1))
        painter.drawRoundedRect(truck, 6, 6)
        painter.setBrush(QtGui.QColor("#2C2C2E"))
        painter.drawEllipse(QtCore.QPointF(truck.left() + 14, truck.bottom() + 2), 5, 5)
        painter.drawEllipse(QtCore.QPointF(truck.right() - 14, truck.bottom() + 2), 5, 5)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor("#D70015"), 2))
        painter.drawRoundedRect(truck.adjusted(-5, -5, 5, 5), 7, 7)
        painter.setPen(QtGui.QColor("#D70015"))
        truck_label_width = 174
        truck_label_x = min(
            int(truck.left() - 4),
            bounds.right() - truck_label_width - 6,
        )
        truck_label_x = max(bounds.left() + 6, truck_label_x)
        painter.drawText(truck_label_x, int(truck.top() - 24), truck_label_width, 20,
                         QtCore.Qt.AlignmentFlag.AlignLeft, f"货车 0.94 · ETA {self.eta_seconds:.1f}s")

        # Rider / helmet marker.
        rider_color = QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF")
        painter.setBrush(rider_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
        painter.drawEllipse(rider, 13, 13)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.drawText(QtCore.QRectF(rider.x() - 10, rider.y() - 10, 20, 20), QtCore.Qt.AlignmentFlag.AlignCenter, "H")
        painter.setPen(QtGui.QColor("#1D1D1F"))
        rider_label_y = min(int(rider.y() + 18), bounds.bottom() - 24)
        painter.drawText(int(rider.x() - 48), rider_label_y, 96, 20,
                         QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop, "骑行者 / 头盔")
        painter.setPen(QtGui.QPen(rider_color, 3))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 20), QtCore.QPointF(rider.x(), rider.y() - 48))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() - 6, rider.y() - 39))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() + 6, rider.y() - 39))

        painter.setPen(QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF"))
        response_label = "已减速 · 6 km/h" if self.rider_slowed else f"正常骑行 · {self.rider_speed_kmh} km/h"
        painter.drawText(
            int(rider.x() - 64), max(bounds.top() + 12, int(rider.y() - 84)), 128, 18,
            QtCore.Qt.AlignmentFlag.AlignHCenter, response_label,
        )

    def _draw_scene_005(self, painter, bounds) -> None:
        """Vertical road: a parked van hides a child from the rider but not from the camera."""
        painter.save()
        painter.translate(bounds.left(), bounds.top())
        geometry = scene_geometry(5, bounds.width(), bounds.height(), progress=self.progress,
                                  rider_progress=self.rider_progress)
        road_x, road_y, road_w, road_h = geometry["road"]
        road_rect = QtCore.QRectF(road_x, road_y, road_w, road_h)
        van_x, van_y, van_w, van_h = geometry["vehicle"]
        van = QtCore.QRectF(van_x, van_y, van_w, van_h)
        rider = QtCore.QPointF(*geometry["rider"])
        child = QtCore.QPointF(*geometry["target"])
        center_x = road_x + road_w * 0.5
        painter.fillRect(road_rect, QtGui.QColor("#60646C"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#D8D8DC"), 2, QtCore.Qt.PenStyle.DashLine))
        painter.drawLine(QtCore.QPointF(center_x, road_y), QtCore.QPointF(center_x, road_y + road_h))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#CFC8BB"))
        painter.drawRect(QtCore.QRectF(road_x + road_w, road_y, bounds.width() * 0.17, road_h))

        painter.setBrush(QtGui.QColor("#F5F5F7"))
        for y in range(int(geometry["cross_y"]), int(geometry["cross_y"] + road_h * 0.12), 14):
            painter.drawRect(QtCore.QRectF(road_x + 4, y, road_w - 8, 7))

        painter.setBrush(QtGui.QColor("#D78732"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#7B4B1C"), 2))
        painter.drawRoundedRect(van, 7, 7)
        painter.setBrush(QtGui.QColor("#B9E0EE"))
        # Front/rear glazing is stacked along the vehicle's travel direction.
        painter.drawRoundedRect(QtCore.QRectF(van.left() + van.width() * 0.16, van.top() + van.height() * 0.10,
                                              van.width() * 0.68, van.height() * 0.20), 3, 3)
        painter.drawRoundedRect(QtCore.QRectF(van.left() + van.width() * 0.16, van.top() + van.height() * 0.39,
                                              van.width() * 0.68, van.height() * 0.20), 3, 3)
        painter.setBrush(QtGui.QColor("#2C2C2E"))
        for wheel_y in (van.top() + van.height() * 0.24, van.top() + van.height() * 0.76):
            painter.drawEllipse(QtCore.QPointF(van.left(), wheel_y), 7, 7)
            painter.drawEllipse(QtCore.QPointF(van.right(), wheel_y), 7, 7)
        painter.setPen(QtGui.QPen(QtGui.QColor("#5C5144"), 1))
        painter.setBrush(QtGui.QColor("#D4C8B6"))
        label_rect = QtCore.QRectF(van.left() - 20, van.top() - 30, van.width() + 40, 24)
        painter.drawRoundedRect(label_rect, 5, 5)
        painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "停靠车辆 · 遮挡视线")

        if self.progress >= 0.12:
            painter.setBrush(QtGui.QColor("#D70015"))
            painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
            painter.drawEllipse(child, 11, 11)
            painter.setPen(QtGui.QColor("#FFFFFF"))
            painter.drawText(QtCore.QRectF(child.x() - 10, child.y() - 10, 20, 20),
                             QtCore.Qt.AlignmentFlag.AlignCenter, "C")
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#D70015"), 2))
            painter.drawRoundedRect(QtCore.QRectF(child.x() - 16, child.y() - 16, 32, 32), 5, 5)
        painter.setPen(QtGui.QColor("#D70015"))
        painter.drawText(int(child.x() - 70), int(child.y() - 32), 140, 20,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, f"儿童 0.94 · ETA {self.eta_seconds:.1f}s")

        blind = QtGui.QPolygonF([rider, QtCore.QPointF(van.left(), van.bottom()), child])
        blind_color = QtGui.QColor("#FF9F0A")
        blind_color.setAlpha(48)
        painter.setBrush(blind_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#C93400"), 2, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(blind)

        camera_pos = QtCore.QPointF(road_x - bounds.width() * 0.16, road_y + road_h * 0.10)
        fov = QtGui.QPolygonF([camera_pos, QtCore.QPointF(child.x(), child.y()),
                               QtCore.QPointF(road_x + road_w, road_y + road_h * 0.58)])
        fov_color = QtGui.QColor("#007AFF")
        fov_color.setAlpha(32)
        painter.setBrush(fov_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#007AFF"), 1, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(fov)
        painter.setBrush(QtGui.QColor("#1D1D1F"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QtCore.QRectF(camera_pos.x() - 13, camera_pos.y() - 8, 26, 16), 4, 4)
        painter.setPen(QtGui.QColor("#1D1D1F"))
        painter.drawText(int(camera_pos.x() + 20), int(camera_pos.y() - 6), 100, 20,
                         QtCore.Qt.AlignmentFlag.AlignLeft, "路侧摄像头")

        rider_color = QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF")
        painter.setBrush(rider_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
        painter.drawEllipse(rider, 13, 13)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.drawText(QtCore.QRectF(rider.x() - 10, rider.y() - 10, 20, 20),
                         QtCore.Qt.AlignmentFlag.AlignCenter, "H")
        painter.setPen(QtGui.QColor("#1D1D1F"))
        painter.drawText(int(rider.x() - 58), int(rider.y() + 20), 116, 20,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, "骑行者 / 头盔")
        painter.setPen(QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF"))
        response_label = "已减速 · 6 km/h" if self.rider_slowed else f"正常骑行 · {self.rider_speed_kmh} km/h"
        painter.drawText(int(rider.x() - 78), max(12, int(rider.y() - 72)), 156, 18,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, response_label)
        painter.setPen(QtGui.QPen(rider_color, 3))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 20), QtCore.QPointF(rider.x(), rider.y() - 48))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() - 6, rider.y() - 39))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() + 6, rider.y() - 39))
        painter.restore()

    def _draw_scene_006(self, painter, bounds) -> None:
        """Vertical road: the opposite lane is closed by a fence and a pedestrian emerges."""
        painter.save()
        painter.translate(bounds.left(), bounds.top())
        geometry = scene_geometry(6, bounds.width(), bounds.height(), progress=self.progress,
                                  rider_progress=self.rider_progress)
        road_x, road_y, road_w, road_h = geometry["road"]
        road_rect = QtCore.QRectF(road_x, road_y, road_w, road_h)
        construction = QtCore.QRectF(*geometry["construction"])
        fence = QtCore.QRectF(*geometry["fence"])
        rider = QtCore.QPointF(*geometry["rider"])
        pedestrian = QtCore.QPointF(*geometry["target"])
        center_x = road_x + road_w * 0.5
        painter.fillRect(road_rect, QtGui.QColor("#60646C"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#D8D8DC"), 2, QtCore.Qt.PenStyle.DashLine))
        painter.drawLine(QtCore.QPointF(center_x, road_y), QtCore.QPointF(center_x, road_y + road_h))
        painter.setBrush(QtGui.QColor("#8C6B43"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#6A4A2D"), 1))
        painter.drawRect(construction)
        painter.setPen(QtGui.QColor("#5C5144"))
        painter.drawText(construction.adjusted(8, 8, -8, -8), QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
                         "对向车道施工封闭")

        painter.setBrush(QtGui.QColor("#3B7DD8"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1D4F91"), 2))
        painter.drawRoundedRect(fence, 4, 4)
        painter.setBrush(QtGui.QColor("#FFFFFF"))
        for y in range(int(fence.top() + 8), int(fence.bottom() - 8), 22):
            painter.drawRect(QtCore.QRectF(fence.left() + 3, y, fence.width() - 6, 10))
        painter.setPen(QtGui.QColor("#1D4F91"))
        painter.drawText(int(fence.left() - 46), int(fence.top() - 10), 100, 18,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, "施工围挡")

        painter.setBrush(QtGui.QColor("#FF6B00"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#B84500"), 1))
        for y in (construction.top() + 35, construction.top() + 92, construction.top() + 149):
            cone = QtGui.QPolygonF([QtCore.QPointF(center_x - 34, y),
                                    QtCore.QPointF(center_x - 46, y + 26),
                                    QtCore.QPointF(center_x - 22, y + 26)])
            painter.drawPolygon(cone)
        painter.setPen(QtGui.QColor("#5C5144"))
        painter.drawText(int(center_x - 84), int(construction.bottom() + 16), 170, 18,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, "本方向车道保持开放")

        if self.progress >= 0.16:
            painter.setBrush(QtGui.QColor("#D70015"))
            painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
            painter.drawEllipse(pedestrian, 11, 11)
            painter.setPen(QtGui.QColor("#FFFFFF"))
            painter.drawText(QtCore.QRectF(pedestrian.x() - 10, pedestrian.y() - 10, 20, 20),
                             QtCore.Qt.AlignmentFlag.AlignCenter, "P")
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#D70015"), 2))
            painter.drawRoundedRect(QtCore.QRectF(pedestrian.x() - 16, pedestrian.y() - 16, 32, 32), 5, 5)
        painter.setPen(QtGui.QColor("#D70015"))
        painter.drawText(int(pedestrian.x() - 64), int(pedestrian.y() - 32), 128, 20,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, f"行人 0.94 · ETA {self.eta_seconds:.1f}s")

        blind = QtGui.QPolygonF([rider, QtCore.QPointF(fence.left(), fence.top() + fence.height() * 0.5), pedestrian])
        blind_color = QtGui.QColor("#FF9F0A")
        blind_color.setAlpha(48)
        painter.setBrush(blind_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#C93400"), 2, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(blind)

        camera_pos = QtCore.QPointF(road_x + road_w + bounds.width() * 0.10, road_y + road_h * 0.10)
        fov = QtGui.QPolygonF([camera_pos, pedestrian,
                               QtCore.QPointF(road_x, road_y + road_h * 0.60)])
        fov_color = QtGui.QColor("#007AFF")
        fov_color.setAlpha(32)
        painter.setBrush(fov_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#007AFF"), 1, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(fov)
        painter.setBrush(QtGui.QColor("#1D1D1F"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QtCore.QRectF(camera_pos.x() - 13, camera_pos.y() - 8, 26, 16), 4, 4)
        painter.setPen(QtGui.QColor("#1D1D1F"))
        painter.drawText(int(camera_pos.x() - 100), int(camera_pos.y() - 6), 90, 20,
                         QtCore.Qt.AlignmentFlag.AlignRight, "路侧摄像头")

        rider_color = QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF")
        painter.setBrush(rider_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
        painter.drawEllipse(rider, 13, 13)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.drawText(QtCore.QRectF(rider.x() - 10, rider.y() - 10, 20, 20),
                         QtCore.Qt.AlignmentFlag.AlignCenter, "H")
        painter.setPen(QtGui.QColor("#1D1D1F"))
        painter.drawText(int(rider.x() - 58), int(rider.y() + 20), 116, 20,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, "骑行者 / 头盔")
        painter.setPen(QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF"))
        response_label = "已减速避让 · 6 km/h" if self.rider_slowed else f"正常骑行 · {self.rider_speed_kmh} km/h"
        painter.drawText(int(rider.x() - 78), max(12, int(rider.y() - 72)), 156, 18,
                         QtCore.Qt.AlignmentFlag.AlignHCenter, response_label)
        painter.setPen(QtGui.QPen(rider_color, 3))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 20), QtCore.QPointF(rider.x(), rider.y() - 48))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() - 6, rider.y() - 39))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() + 6, rider.y() - 39))
        painter.restore()


class _ScenarioStage(QtWidgets.QFrame):
    def __init__(self, index: int, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scenarioStage")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        header = QtWidgets.QHBoxLayout()
        self.dot = QtWidgets.QLabel("●")
        self.dot.setObjectName("stageDot")
        title_label = QtWidgets.QLabel(f"{index:02d}  {title}")
        title_label.setObjectName("mappingLabel")
        header.addWidget(self.dot)
        header.addWidget(title_label, 1)
        self.meta = QtWidgets.QLabel("等待")
        self.meta.setObjectName("monoMuted")
        self.meta.setWordWrap(True)
        layout.addLayout(header)
        layout.addWidget(self.meta)
        self.set_state("等待", "waiting")

    def set_state(self, text: str, state: str) -> None:
        color = _COLORS.get(state, _COLORS["waiting"])
        self.meta.setText(text)
        self.dot.setStyleSheet(f"color: {color}; background: transparent;")
        self.setProperty("stageState", state)
        self.style().unpolish(self)
        self.style().polish(self)


class CooperativeScenarioPanel(QtWidgets.QWidget):
    start_requested = QtCore.Signal(dict)
    reset_requested = QtCore.Signal()
    scene_dispatch_requested = QtCore.Signal(int)
    demo_mode_requested = QtCore.Signal()
    restore_real_requested = QtCore.Signal()

    EVENT_DURATION_MS = 5000
    CLOUD_DISPATCH_MS = 850

    @staticmethod
    def has_simulated_input() -> bool:
        """The visual input is a labelled demo; the downstream hardware path is real."""
        return True

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = False
        self._dispatched = False
        self._ack_received = False
        self._ack_remaining_ms: int | None = None
        self._ack_elapsed_ms: int | None = None
        self._ack_is_simulated = False
        self._active_scene_id = 0
        self.current_event_id = ""
        self._link_ready = False
        self._demo_mode = False
        self._reduced_motion = False
        self._clock = QtCore.QElapsedTimer()
        self._last_elapsed_ms = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        heading = QtWidgets.QFrame()
        heading.setObjectName("pageHeader")
        h = QtWidgets.QHBoxLayout(heading)
        h.setContentsMargins(16, 11, 16, 11)
        labels = QtWidgets.QVBoxLayout()
        labels.setSpacing(2)
        title = QtWidgets.QLabel("三场景真实后段响应演示")
        title.setObjectName("pageTitle")
        warning = QtWidgets.QLabel("⚠ 演示输入，后段实物执行 — DFPlayer 语音 / RGB 警示 / 气泵充气均为真实硬件响应")
        warning.setObjectName("demoWarning")
        warning.setWordWrap(True)
        detail = QtWidgets.QLabel("前段动画模拟摄像头→云端→PC 数据流；后段真实下发 ESP32，以 DFPlayer、显示器/RGB、气泵与压力遥测证明实际响应")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        labels.addWidget(title)
        labels.addWidget(warning)
        labels.addWidget(detail)
        h.addLayout(labels, 1)
        button_group = QtWidgets.QVBoxLayout()
        button_group.setSpacing(4)
        self.mode_button = QtWidgets.QPushButton("进入模拟模式")
        self.mode_button.setObjectName("primaryAction")
        self.mode_button.clicked.connect(self._toggle_operating_mode)
        button_group.addWidget(self.mode_button)
        self.scene_buttons: dict[int, QtWidgets.QPushButton] = {}
        for scene_id in (4, 5, 6):
            cfg = SCENARIOS[scene_id]
            display_index = scene_id - 3
            btn = QtWidgets.QPushButton(f"场景{display_index} · {cfg['title']} · {cfg['subtitle']}")
            btn.setObjectName("primaryAction")
            btn.clicked.connect(lambda checked, s=scene_id: self.begin_demo(s))
            self.scene_buttons[scene_id] = btn
            button_group.addWidget(btn)
        self.reset_button = QtWidgets.QPushButton("复位")
        self.reset_button.clicked.connect(self.reset_demo)
        button_group.addWidget(self.reset_button)
        h.addLayout(button_group)
        root.addWidget(heading)

        content = QtWidgets.QHBoxLayout()
        content.setSpacing(10)
        map_panel = QtWidgets.QFrame()
        map_panel.setObjectName("scenePanel")
        map_layout = QtWidgets.QVBoxLayout(map_panel)
        map_layout.setContentsMargins(12, 10, 12, 12)
        map_head = QtWidgets.QHBoxLayout()
        map_title = QtWidgets.QLabel("路口态势")
        map_title.setObjectName("columnTitle")
        self.map_badge = QtWidgets.QLabel("● 等待演示")
        self.map_badge.setObjectName("softBadge")
        map_head.addWidget(map_title)
        map_head.addStretch(1)
        map_head.addWidget(self.map_badge)
        self.road_map = _ScenarioMap(4)
        map_layout.addLayout(map_head)
        map_layout.addWidget(self.road_map, 1)
        self._map_container = map_layout
        content.addWidget(map_panel, 2)

        side = QtWidgets.QFrame()
        side.setObjectName("scenePanel")
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(14, 12, 14, 12)
        side_layout.setSpacing(9)
        side_title = QtWidgets.QLabel("实时协同链路")
        side_title.setObjectName("columnTitle")
        side_layout.addWidget(side_title)
        eta_card = QtWidgets.QFrame()
        eta_card.setObjectName("etaCard")
        eta_layout = QtWidgets.QVBoxLayout(eta_card)
        eta_layout.setContentsMargins(14, 12, 14, 12)
        self.eta_caption = QtWidgets.QLabel("货车预计到达路口")
        self.eta_caption.setObjectName("metricTitle")
        self.eta_value = QtWidgets.QLabel("5.0 秒")
        self.eta_value.setObjectName("etaValue")
        self.deadline_value = QtWidgets.QLabel("ESP32 必须在倒计时结束前响应")
        self.deadline_value.setObjectName("muted")
        self.deadline_value.setWordWrap(True)
        eta_layout.addWidget(self.eta_caption)
        eta_layout.addWidget(self.eta_value)
        eta_layout.addWidget(self.deadline_value)
        side_layout.addWidget(eta_card)
        self.detection_value = self._info_card("摄像头检测", "等待检测")
        self.cloud_status = self._info_card("云端预测", "等待上传")
        self.helmet_status = self._info_card("头盔 ESP32", "等待下发")
        self.rider_status = self._info_card("骑行者响应", "正常骑行 · 18 km/h")
        self.protection_status = self._info_card("提示与保护动作", "等待 ESP32 确认")
        side_layout.addWidget(self.detection_value[0])
        side_layout.addWidget(self.cloud_status[0])
        side_layout.addWidget(self.helmet_status[0])
        side_layout.addWidget(self.rider_status[0])
        side_layout.addWidget(self.protection_status[0])
        side_layout.addStretch(1)
        self.event_value = self._value("事件 ID · 等待演示")
        self.network_value = self._value("网络耗时 · —")
        self.rgb_value = self._value("RGB · 等待 ACK")
        self.voice_value = self._value("语音 · 等待真实反馈")
        self.serial_status = self._value("串口状态 · 等待")
        for value in (self.event_value, self.network_value, self.rgb_value, self.voice_value, self.serial_status):
            value.setWordWrap(True)
            side_layout.addWidget(value)
        content.addWidget(side, 1)
        root.addLayout(content, 1)

        stages = QtWidgets.QHBoxLayout()
        stages.setSpacing(7)
        self.stages = [
            _ScenarioStage(1, "监控发现"), _ScenarioStage(2, "上传云端"),
            _ScenarioStage(3, "云端预测"), _ScenarioStage(4, "下发头盔"),
            _ScenarioStage(5, "ESP32 响应"),
        ]
        for stage in self.stages:
            stages.addWidget(stage, 1)
        root.addLayout(stages)
        self._reset_state(emit_signal=False)

    @staticmethod
    def _info_card(title: str, initial: str) -> tuple[QtWidgets.QFrame, QtWidgets.QLabel]:
        card = QtWidgets.QFrame()
        card.setObjectName("scenarioInfoCard")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(3)
        caption = QtWidgets.QLabel(title)
        caption.setObjectName("metricTitle")
        value = QtWidgets.QLabel(initial)
        value.setObjectName("mappingValue")
        value.setWordWrap(True)
        layout.addWidget(caption)
        layout.addWidget(value)
        return card, value

    @staticmethod
    def _value(text: str) -> QtWidgets.QLabel:
        value = QtWidgets.QLabel(text)
        value.setObjectName("monoMuted")
        return value

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = enabled
        self.road_map.reduced_motion = enabled
        self._timer.setInterval(160 if enabled else 33)

    def set_link_ready(self, ready: bool) -> None:
        """Called when the chain client confirms ESP32 frames are being received."""
        self._link_ready = ready

    def set_operating_mode(self, mode: str, *, lease_remaining_ms: int = 0) -> None:
        self._demo_mode = mode == "demo"
        if self._demo_mode:
            self.mode_button.setText("恢复真实链路")
            self.mode_button.setToolTip(f"模拟通道租约剩余 {max(0, lease_remaining_ms) / 1000:.1f} 秒")
            if not self._running:
                for button in self.scene_buttons.values():
                    button.setEnabled(True)
            self.map_badge.setText("● 模拟通道已启用 · 真实下发已暂停")
        else:
            self.mode_button.setText("进入模拟模式")
            self.mode_button.setToolTip("恢复摄像头→云端→PC→ESP32真实链路")
            for button in self.scene_buttons.values():
                button.setEnabled(False)
            if not self._running:
                self.map_badge.setText("● 真实链路已恢复")

    def _toggle_operating_mode(self) -> None:
        if self._demo_mode:
            self.restore_real_requested.emit()
        else:
            self.demo_mode_requested.emit()

    def begin_demo(self, scene_id: int = 4) -> None:
        if self._running:
            return
        if not self._demo_mode and not self._link_ready:
            self.stages[3].set_state("请先进入模拟模式 · 链路未就绪", "failed")
            self.helmet_status[1].setText("模拟通道未启用，真实链路不会被场景演示占用")
            self.map_badge.setText("● 请先进入模拟模式")
            return
        self._active_scene_id = scene_id
        self._replace_road_map(scene_id)
        self.current_event_id = f"scenario-{scene_id:03d}-{uuid.uuid4().hex[:8]}"
        self._running = True
        self._dispatched = False
        self._ack_received = False
        self._ack_remaining_ms = None
        self._ack_elapsed_ms = None
        self._ack_is_simulated = False
        self._last_elapsed_ms = 0
        self._clock.start()
        for btn in self.scene_buttons.values():
            btn.setEnabled(False)
        self.event_value.setText(f"事件 ID · {self.current_event_id}")
        self._update_from_elapsed(0)
        self._timer.start()

    def _replace_road_map(self, scene_id: int) -> None:
        """Swap the animated map to match the selected scene layout."""
        old = self.road_map
        new_map = _ScenarioMap(scene_id)
        new_map.reduced_motion = self._reduced_motion
        idx = self._map_container.indexOf(old)
        if idx >= 0:
            self._map_container.insertWidget(idx, new_map)
        old.deleteLater()
        self.road_map = new_map

    def reset_demo(self) -> None:
        self._reset_state(emit_signal=True)

    def _reset_state(self, *, emit_signal: bool) -> None:
        self._timer.stop()
        self._running = False
        self._dispatched = False
        self._ack_received = False
        self._ack_remaining_ms = None
        self._ack_elapsed_ms = None
        self._ack_is_simulated = False
        self._active_scene_id = 0
        self.current_event_id = ""
        self._last_elapsed_ms = 0
        for btn in self.scene_buttons.values():
            btn.setEnabled(self._demo_mode)
        for stage in self.stages:
            stage.set_state("等待", "waiting")
        self.eta_value.setText("5.0 秒")
        self.deadline_value.setText("ESP32 必须在倒计时结束前响应")
        self.event_value.setText("事件 ID · 等待演示")
        self.network_value.setText("网络耗时 · —")
        self.rgb_value.setText("RGB · 等待 ACK")
        self.voice_value.setText("语音 · 等待真实反馈")
        self.serial_status.setText("串口状态 · 等待")
        self.detection_value[1].setText("等待检测")
        self.cloud_status[1].setText("等待上传")
        self.helmet_status[1].setText("等待下发")
        self.rider_status[1].setText("等待 ESP32 确认")
        self.protection_status[1].setText("等待真实 DFPlayer 与泵阀状态")
        self.map_badge.setText("● 等待演示")
        self.road_map.set_state(0.0, 5.0, "等待演示")
        if emit_signal:
            self.reset_requested.emit()

    def _tick(self) -> None:
        if self._running:
            self._update_from_elapsed(self._clock.elapsed())

    def _update_from_elapsed(self, elapsed_ms: int) -> None:
        """Authoritative timeline entry point; tests can drive it without sleeping."""
        if not self._running:
            return
        elapsed_ms = max(0, int(elapsed_ms))
        self._last_elapsed_ms = elapsed_ms
        remaining_ms = max(0, self.EVENT_DURATION_MS - elapsed_ms)
        eta = remaining_ms / 1000.0
        progress = min(1.0, elapsed_ms / self.EVENT_DURATION_MS)
        cfg = SCENARIOS.get(self._active_scene_id, SCENARIOS[4])
        target = cfg["target"]
        self.eta_caption.setText(f"{target}预计到达")

        if elapsed_ms < 260:
            phase = f"路侧摄像头锁定{target}"
            self.stages[0].set_state(f"{target} · 置信度 0.94", "active")
            self.detection_value[1].setText(f"{target} · 置信度 0.94")
            self.map_badge.setText(f"● 已发现{target}")
        elif elapsed_ms < 560:
            phase = "检测结果正在上传云端"
            self.stages[0].set_state(f"{target}检测完成 · 0.94", "completed")
            self.stages[1].set_state("正在上传检测事件", "active")
            self.cloud_status[1].setText("正在上传目标和场景数据")
        elif elapsed_ms < self.CLOUD_DISPATCH_MS:
            phase = "云端正在分析场景"
            self.stages[0].set_state(f"{target}检测完成 · 0.94", "completed")
            self.stages[1].set_state("上传完成", "completed")
            self.stages[2].set_state(f"场景分析 · {cfg['severity']}", "active")
            self.cloud_status[1].setText(f"识别为{cfg['title']}场景")
        else:
            phase = "预警已下发，等待 ESP32 真实响应"
            self.stages[0].set_state(f"{target}检测完成 · 0.94", "completed")
            self.stages[1].set_state("上传完成", "completed")
            self.stages[2].set_state(f"场景确认 · {cfg['severity']}", "completed")
            self.cloud_status[1].setText(f"已确认{cfg['title']}场景 · 正在真实下发")
            if not self._dispatched:
                self._dispatched = True
                if self._demo_mode and self._link_ready:
                    self.stages[3].set_state("正在真实下发到 ESP32", "active")
                    self.helmet_status[1].setText("通过 /risk 链路下发，等待 ESP32 ACK")
                    self.scene_dispatch_requested.emit(self._active_scene_id)
                else:
                    self.stages[3].set_state("模拟通道未就绪 · 跳过下发", "failed")
                    self.helmet_status[1].setText("请先进入模拟模式并确认头盔最新帧")
                    self.map_badge.setText("● 模拟通道未就绪，未执行硬件动作")
                    self.deadline_value.setText("模拟通道未就绪；动画仅用于演示，未触发硬件")
            if not self._ack_received:
                self.stages[4].set_state(f"等待 ESP32 响应 · 剩余 {eta:.1f} 秒", "waiting")

        self.eta_value.setText(f"{eta:.1f} 秒")
        self.road_map.set_state(
            progress, eta, phase,
            rider_progress=min(0.82, progress * 0.82),
            rider_slowed=self._ack_received,
            rider_speed_kmh=6 if self._ack_received else 18,
        )
        if remaining_ms <= 0:
            self._running = False
            self._timer.stop()
            if self._ack_received:
                self.deadline_value.setText(f"ESP32 已提前 {self._ack_remaining_ms / 1000.0:.1f} 秒完成响应")
            else:
                self.stages[4].set_state("响应超时 · 未在期限内确认", "failed")
                self.helmet_status[1].setText("响应超时：未收到有效 ESP32 ACK")
                self.deadline_value.setText("倒计时结束，当前演示响应失败")
                self.map_badge.setText("● 响应超时")

    def apply_chain_state(self, state: dict) -> None:
        hazard = state.get("road_hazard") if isinstance(state, dict) else None
        if not isinstance(hazard, dict) or not hazard.get("event_id"):
            return
        event_id = str(hazard.get("event_id"))
        if self.current_event_id and event_id != self.current_event_id:
            return
        if not self.current_event_id:
            self.current_event_id = event_id
        self.event_value.setText(f"事件 ID · {event_id}")
        delivery = hazard.get("delivery", {}) if isinstance(hazard.get("delivery"), dict) else {}
        attempts = int(hazard.get("attempts", 0) or 0)
        delivery_state = str(delivery.get("state", "waiting"))
        if delivery_state == "completed":
            self.stages[3].set_state("下发完成", "completed")
            self.helmet_status[1].setText("命令已下发，等待 ESP32 返回有效 ACK")
        elif delivery_state == "failed":
            self.stages[3].set_state(f"下发失败 · 已重试 {attempts} 次", "failed")
            self.helmet_status[1].setText(str(hazard.get("error") or "下发失败，ESP32 可能离线"))
        elif delivery_state == "active":
            self.stages[3].set_state(f"下发中 · 第 {attempts + 1} 次", "active")

        ack = hazard.get("ack", {}) if isinstance(hazard.get("ack"), dict) else {}
        payload = ack.get("payload") if isinstance(ack, dict) else None
        real_ack = (
            isinstance(payload, dict) and payload.get("type") == "road_hazard_ack"
            and payload.get("accepted") is True and payload.get("event_id") == event_id
        )
        elapsed = max(
            self._last_elapsed_ms,
            self._clock.elapsed() if self._running and self._clock.isValid() else 0,
        )
        if real_ack and elapsed < self.EVENT_DURATION_MS:
            self._accept_response(elapsed, simulated=False)
            voice_state = str(payload.get("voice_state") or "not_requested")
            self.voice_value.setText(f"语音 · {voice_state}")
        elif real_ack:
            self.stages[4].set_state("收到 ACK，但已超过到达期限", "failed")
            self.helmet_status[1].setText("响应超时：ACK 晚于货车到达时间")
        elif delivery_state == "failed" or ack.get("state") == "failed":
            self.stages[4].set_state("未确认 · ESP32 离线或拒绝", "failed")
        latency = hazard.get("network_latency_ms")
        self.network_value.setText(f"网络耗时 · {int(latency)} 毫秒" if isinstance(latency, (int, float)) else "网络耗时 · —")
        pattern = str(hazard.get("effective_rgb_pattern") or "")
        self.rgb_value.setText(f"RGB · {pattern}" if pattern else "RGB · 等待 ACK")

    def apply_submission_error(self, message: str) -> None:
        """Expose real service rejection instead of leaving a simulated success state."""
        if not self.current_event_id:
            return
        detail = (message or "服务拒绝").replace("\n", " ")
        self.stages[3].set_state(f"下发失败 · {detail}", "failed")
        self.stages[4].set_state("未确认 · 未到达 ESP32", "failed")
        self.helmet_status[1].setText(message or "服务拒绝场景事件")
        self.deadline_value.setText("下发失败；倒计时继续，仅用于观察动画过程")
        self.map_badge.setText("● 下发失败")

    def apply_demo_reset_result(self, result: dict) -> None:
        if not self._demo_mode:
            return
        self.map_badge.setText("● ESP32 已接收复位，等待真实泄压")
        self.helmet_status[1].setText("模拟动作已复位 · 等待泵阀与压力遥测")
        self.protection_status[1].setText("等待真实气动泄压反馈")

    def apply_mode_error(self, message: str) -> None:
        self.mode_button.setEnabled(True)
        self.map_badge.setText("● 模拟通道切换失败")
        self.helmet_status[1].setText(message or "模拟通道切换失败")

    def apply_dispatch_result(self, result: dict) -> None:
        """Real ESP32 ACK received from scenario dispatch."""
        if not self.current_event_id or not self._running:
            return
        elapsed = max(self._last_elapsed_ms,
                      self._clock.elapsed() if self._clock.isValid() else 0)
        self._accept_response(elapsed)
        ack = result.get("ack", {})
        if isinstance(ack, dict):
            pattern = str(ack.get("effective_rgb_pattern") or ack.get("rgb_pattern") or "")
            self.rgb_value.setText(f"RGB · {pattern}" if pattern else "RGB · ACK 已确认")
            voice = ack.get("voice_ack", {})
            if isinstance(voice, dict):
                status = str(voice.get("status", ""))
                self.voice_value.setText(f"语音 · {status}")
        self.helmet_status[1].setText("ESP32 已响应 · 等待实物执行反馈")

    def _accept_response(self, elapsed_ms: int) -> None:
        """Record a real ESP32 ACK response."""
        self._ack_received = True
        self._ack_is_simulated = False
        self._ack_remaining_ms = self.EVENT_DURATION_MS - elapsed_ms
        self._ack_elapsed_ms = elapsed_ms
        remaining = self._ack_remaining_ms / 1000.0
        self.stages[3].set_state("下发完成", "completed")
        self.stages[4].set_state(f"ESP32 已响应 · 提前 {remaining:.1f} 秒", "completed")
        self.helmet_status[1].setText(f"ESP32 已响应 · 剩余安全时间 {remaining:.1f} 秒")
        self.deadline_value.setText(f"ESP32 已在期限前响应，剩余 {remaining:.1f} 秒")
        self.map_badge.setText("● ESP32 已响应")

    def apply_serial_status(self, event) -> None:
        self.serial_status.setText(f"串口状态 · {event.state} · {event.event_id or '—'}")
        if event.effective_rgb_pattern:
            self.rgb_value.setText(f"RGB · {event.effective_rgb_pattern}")

    def apply_voice_status(self, event) -> None:
        """Real DFPlayer feedback takes precedence over the illustrative timeline."""
        state = str(event.state or "unknown")
        track = f" · 曲目 {event.track}" if getattr(event, "track", None) is not None else ""
        self.voice_value.setText(f"语音 · {state}{track}")
        if state in {"playing", "completed", "done"}:
            self.protection_status[1].setText("收到真实 DFPlayer 反馈")

    def apply_pneumatic_status(self, event) -> None:
        """Surface true pump/valve telemetry without pretending an animation is hardware proof."""
        if bool(getattr(event, "self_test_failed", False)):
            self.protection_status[1].setText("气动自检失败 · 压力未上升 · 自动充气已锁止")
            return
        pump = "开" if bool(getattr(event, "pump_on", False)) else "关"
        valve = "开" if bool(getattr(event, "valve_on", False)) else "关"
        state = str(getattr(event, "state", "未知"))
        self.protection_status[1].setText(f"真实气动反馈 · {state} · 泵 {pump} / 阀 {valve}")
