from __future__ import annotations

from PySide6 import QtCore, QtNetwork


def build_get_request(url: str, *, timeout_ms: int = 4000) -> QtNetwork.QNetworkRequest:
    request = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
    request.setTransferTimeout(timeout_ms)
    request.setAttribute(
        QtNetwork.QNetworkRequest.Attribute.CacheLoadControlAttribute,
        QtNetwork.QNetworkRequest.CacheLoadControl.AlwaysNetwork,
    )
    return request
