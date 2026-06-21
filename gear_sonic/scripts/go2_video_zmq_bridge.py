"""
Go2 front-camera RPC bridge -> ZMQ PUB for ComposedCameraClientSensor.

go2_video_client pulls JPEG frames via Unitree RPC (videohub / GetImageSample).
This script republishes them on the same ZMQ/msgpack wire format used by
gear_sonic.camera.composed_camera (ImageMessageSchema + SensorServer).

Typical layout (bridge on the machine connected to Go2):

    # Terminal 1 — ego-only bridge (RPC in, ZMQ out)
    python gear_sonic/scripts/go2_video_zmq_bridge.py --network-interface enP8p1s

    # Terminal 2 — any ComposedCamera client
    python gear_sonic/scripts/run_camera_viewer.py --camera-host localhost --camera-port 5555

For Go2 ego + wrist OAK cameras together, prefer a single composed_camera server::

    python -m gear_sonic.camera.composed_camera \\
        --ego-view-camera go2 --ego-view-device-id enP8p1s \\
        --left-wrist-camera oak --left-wrist-device-id <LEFT_MXID> \\
        --right-wrist-camera oak --right-wrist-device-id <RIGHT_MXID> \\
        --port 5555

Dependencies:
    pip install -e external_dependencies/unitree_sdk2_python
    pip install -e gear_sonic   # or repo install_scripts for data collection venv
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional

import tyro

from gear_sonic.camera.sensor_server import ImageMessageSchema, SensorServer


@dataclass
class Go2VideoZmqBridgeConfig:
    """CLI config for the Go2 RPC -> ZMQ bridge."""

    port: int = 5555
    """ZMQ PUB port (ComposedCameraClientSensor connects here)."""

    fps: int = 30
    """Publish rate. Go2 RPC is ~30 Hz; lower values add latency."""

    network_interface: Optional[str] = None
    """DDS network interface connected to Go2 (e.g. enP8p1s). None = default."""

    image_key: str = "ego_view"
    """Image key in ImageMessageSchema (matches composed_camera mount names)."""

    timeout: float = 3.0
    """RPC timeout in seconds for VideoClient.GetImageSample."""

    send_jpeg_bytes: bool = True
    """Send raw JPEG bytes on the wire (faster). False = decode and send RGB numpy."""


class Go2VideoZmqBridge(SensorServer):
    """ZMQ publisher fed by Go2 VideoClient RPC."""

    def __init__(self, config: Go2VideoZmqBridgeConfig):
        self.config = config
        self._video_client = None
        self.start_server(config.port)

    def _init_video_client(self):
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.go2.video.video_client import VideoClient

        if self.config.network_interface:
            ChannelFactoryInitialize(0, self.config.network_interface)
        else:
            ChannelFactoryInitialize(0)

        client = VideoClient()
        client.SetTimeout(self.config.timeout)
        client.Init()
        self._video_client = client
        print(
            f"Go2 VideoClient ready (interface={self.config.network_interface or 'default'}, "
            f"timeout={self.config.timeout}s)"
        )

    def run(self):
        self._init_video_client()

        idx = 0
        server_start_time = time.monotonic()
        fps_print_time = time.monotonic()
        frame_interval = 1.0 / self.config.fps
        consecutive_errors = 0

        print(
            f"Publishing Go2 front camera as '{self.config.image_key}' "
            f"on tcp://*:{self.config.port} at {self.config.fps} Hz"
        )

        while True:
            target_time = server_start_time + (idx + 1) * frame_interval

            code, data = self._video_client.GetImageSample()
            if code != 0:
                consecutive_errors += 1
                if consecutive_errors == 1 or consecutive_errors % 20 == 0:
                    print(
                        f"[WARN] GetImageSample failed, code={code} "
                        f"(streak={consecutive_errors})"
                    )
                time.sleep(0.01)
                idx += 1
                continue

            consecutive_errors = 0
            capture_time = time.time()
            jpeg_bytes = bytes(data)

            if self.config.send_jpeg_bytes:
                payload = jpeg_bytes
            else:
                import cv2
                import numpy as np

                bgr = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                if bgr is None:
                    time.sleep(0.001)
                    idx += 1
                    continue
                payload = bgr[..., ::-1]  # RGB for ImageMessageSchema numpy path

            schema = ImageMessageSchema(
                timestamps={self.config.image_key: capture_time},
                images={self.config.image_key: payload},
            )
            self.send_message(schema.serialize())
            idx += 1

            if idx % 10 == 0:
                elapsed = time.monotonic() - fps_print_time
                if elapsed > 0:
                    print(f"Bridge publish FPS: {10 / elapsed:.2f}")
                fps_print_time = time.monotonic()

            sleep_time = target_time - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)


def main(config: Go2VideoZmqBridgeConfig):
    bridge = Go2VideoZmqBridge(config)
    try:
        bridge.run()
    except KeyboardInterrupt:
        print("Stopping Go2 video bridge...")
    finally:
        bridge.stop_server()


if __name__ == "__main__":
  main(tyro.cli(Go2VideoZmqBridgeConfig))