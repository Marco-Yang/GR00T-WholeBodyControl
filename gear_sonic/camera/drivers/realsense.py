"""Intel RealSense camera driver.

Requires the ``pyrealsense2`` SDK — install with::

    pip install pyrealsense2

See https://github.com/IntelRealSense/librealsense for hardware-specific instructions.
"""

import time
from typing import Any

import cv2
import numpy as np

try:
    import gymnasium as gym
except ImportError:
    gym = None  # type: ignore[assignment]

import pyrealsense2 as rs

from gear_sonic.camera.sensor import Sensor
from gear_sonic.camera.sensor_server import (
    CameraMountPosition,
    ImageMessageSchema,
    SensorServer,
)


class RealSenseConfig:
    """Configuration for the RealSense camera."""

    depth_image_dim: tuple[int, int] = (640, 480)
    color_image_dim: tuple[int, int] = (640, 480)
    fps: int = 30
    mount_position: str = CameraMountPosition.EGO_VIEW.value
    enable_depth: bool = True
    """When False, only publish the color stream (lower USB/CPU load)."""

    wire_jpeg: bool = False
    """Publish color as JPEG bytes on ZMQ instead of RGB numpy (less CPU on server)."""

    jpeg_quality: int = 80
    """JPEG quality when wire_jpeg is enabled."""


class RealSenseSensor(Sensor, SensorServer):
    """Sensor for Intel RealSense depth cameras."""

    def __init__(
        self,
        run_as_server: bool = False,
        port: int = 5555,
        config: RealSenseConfig = RealSenseConfig(),
        id: int = 0,
        mount_position: str = CameraMountPosition.EGO_VIEW.value,
        device_id: str | None = None,
        enable_depth: bool | None = None,
    ):
        devices = list(rs.context().query_devices())
        if len(devices) == 0:
            raise RuntimeError("No RealSense devices found")

        for device in devices:
            print(f"Device: {device.get_info(rs.camera_info.name)}")
            print(f"    Serial number: {device.get_info(rs.camera_info.serial_number)}")
            print(f"    Firmware version: {device.get_info(rs.camera_info.firmware_version)}")

        if device_id is not None:
            selected = None
            for device in devices:
                serial = device.get_info(rs.camera_info.serial_number)
                if serial == device_id:
                    selected = device
                    break
            if selected is None:
                raise RuntimeError(
                    f"RealSense serial {device_id} not found. "
                    f"Available: {[d.get_info(rs.camera_info.serial_number) for d in devices]}"
                )
        else:
            devices = sorted(devices, key=lambda x: x.get_info(rs.camera_info.serial_number))
            selected = devices[id]

        selected_serial = selected.get_info(rs.camera_info.serial_number)

        if enable_depth is not None:
            config.enable_depth = enable_depth

        self.pipeline = rs.pipeline()
        rs_config = rs.config()
        rs_config.enable_device(selected_serial)

        try:
            rs_config.enable_stream(
                rs.stream.color,
                config.color_image_dim[0],
                config.color_image_dim[1],
                rs.format.rgb8,
                config.fps,
            )
            if config.enable_depth:
                rs_config.enable_stream(
                    rs.stream.depth,
                    config.depth_image_dim[0],
                    config.depth_image_dim[1],
                    rs.format.z16,
                    config.fps,
                )
            self.pipeline.start(rs_config)
        except Exception as e:
            raise RuntimeError(f"Failed to start RealSense pipeline: {e}")

        self._realsense_config = config
        self._run_as_server = run_as_server
        self.mount_position = mount_position
        if self._run_as_server:
            self.start_server(port)
        depth_note = "color+depth" if config.enable_depth else "color only"
        if config.wire_jpeg and not config.enable_depth:
            depth_note += ", wire jpeg"
        print(
            f"Done initializing RealSense sensor: "
            f"{selected_serial} (mount={mount_position}, {depth_note})"
        )

    def read(self) -> dict[str, Any] | None:
        try:
            frames = self.pipeline.wait_for_frames()
        except Exception as e:
            print(f"ERROR! Failed to wait for frames: {e}")
            return None

        color_frame = frames.get_color_frame()

        if not color_frame:
            print("WARNING! No color frame")
            return None

        try:
            color_image = np.asanyarray(color_frame.get_data())
        except Exception as e:
            print(f"ERROR! Failed to convert color frame to numpy array: {e}")
            return None

        if color_image.size == 0:
            print("WARNING! Empty color image")
            return None

        current_time = time.time()
        timestamps = {self.mount_position: current_time}

        if self._realsense_config.wire_jpeg and not self._realsense_config.enable_depth:
            bgr = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)
            ok, buf = cv2.imencode(
                ".jpg",
                bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), self._realsense_config.jpeg_quality],
            )
            if not ok:
                return None
            images = {self.mount_position: buf.tobytes()}
        else:
            images = {self.mount_position: color_image}

        if self._realsense_config.enable_depth:
            depth_frame = frames.get_depth_frame()
            if not depth_frame:
                print("WARNING! No depth frame")
                return None
            try:
                depth_image = np.asanyarray(depth_frame.get_data())
            except Exception as e:
                print(f"ERROR! Failed to convert depth frame to numpy array: {e}")
                return None
            if depth_image.size == 0:
                print("WARNING! Empty depth image")
                return None
            depth_key = f"{self.mount_position}_depth"
            timestamps[depth_key] = current_time
            images[depth_key] = depth_image

        return {"timestamps": timestamps, "images": images}

    def serialize(self, data: dict[str, Any]) -> dict[str, Any]:
        serialized_msg = ImageMessageSchema(timestamps=data["timestamps"], images=data["images"])
        return serialized_msg.serialize()

    def observation_space(self):
        if gym is None:
            return None
        spaces = {
            "color_image": gym.spaces.Box(
                low=0,
                high=255,
                shape=(
                    self._realsense_config.color_image_dim[1],
                    self._realsense_config.color_image_dim[0],
                    3,
                ),
                dtype=np.uint8,
            ),
        }
        if self._realsense_config.enable_depth:
            spaces["depth_image"] = gym.spaces.Box(
                low=0,
                high=255,
                shape=(
                    self._realsense_config.depth_image_dim[1],
                    self._realsense_config.depth_image_dim[0],
                    1,
                ),
                dtype=np.uint16,
            )
        return gym.spaces.Dict(spaces)

    def close(self):
        if self._run_as_server:
            self.stop_server()
        self.pipeline.stop()

    def run_server(self):
        if not self._run_as_server:
            raise ValueError("run_as_server must be True to call run_server()")
        while True:
            read_result = self.read()
            if read_result is None:
                continue
            self.send_message({self.mount_position: self.serialize(read_result)})
