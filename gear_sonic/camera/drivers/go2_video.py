"""Go2 front camera via Unitree RPC (videohub / GetImageSample).

Use camera_type ``go2`` in composed_camera. ``device_id`` is the optional DDS
network interface connected to the robot (e.g. ``enP8p1s``).
"""

import time
from typing import Any

import cv2
import numpy as np

try:
    import gymnasium as gym
except ImportError:
    gym = None  # type: ignore[assignment]

from gear_sonic.camera.sensor import Sensor
from gear_sonic.camera.sensor_server import ImageMessageSchema


class Go2VideoSensor(Sensor):
    """Pulls JPEG frames from Go2 VideoClient and exposes them as ego_view RGB."""

    _channel_initialized: bool = False

    def __init__(
        self,
        mount_position: str = "ego_view",
        network_interface: str | None = None,
        timeout: float = 3.0,
    ):
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.go2.video.video_client import VideoClient

        if not Go2VideoSensor._channel_initialized:
            if network_interface:
                ChannelFactoryInitialize(0, network_interface)
            else:
                ChannelFactoryInitialize(0)
            Go2VideoSensor._channel_initialized = True

        self.mount_position = mount_position
        self._client = VideoClient()
        self._client.SetTimeout(timeout)
        self._client.Init()
        self._image_shape: tuple[int, int, int] | None = None

        print(
            f"[{mount_position}] Go2 VideoClient ready "
            f"(interface={network_interface or 'default'}, timeout={timeout}s)"
        )

    def read(self) -> dict[str, Any] | None:
        code, data = self._client.GetImageSample()
        if code != 0:
            return None

        jpeg_bytes = bytes(data)
        if not jpeg_bytes:
            return None

        # Pass JPEG through to ZMQ without decode/re-encode (saves CPU on server).
        if self._image_shape is None:
            probe = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if probe is not None:
                self._image_shape = probe.shape

        capture_time = time.time()
        return {
            "timestamps": {self.mount_position: capture_time},
            "images": {self.mount_position: jpeg_bytes},
        }

    def serialize(self, data: dict[str, Any]) -> dict[str, Any]:
        schema = ImageMessageSchema(timestamps=data["timestamps"], images=data["images"])
        return schema.serialize()

    def observation_space(self):
        if gym is None:
            return None
        shape = self._image_shape or (480, 640, 3)
        return gym.spaces.Dict(
            {
                "color_image": gym.spaces.Box(
                    low=0,
                    high=255,
                    shape=shape,
                    dtype=np.uint8,
                ),
            }
        )

    def close(self):
        pass
