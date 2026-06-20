"""
Mock PICO client: connects to RoboticsServiceProcess on port 63901,
sends CONNECT + device state JSON with Body data, checks if SDK receives it.
"""
import os
# Bypass HTTP proxy so gRPC connects to 127.0.0.1:60061 directly
os.environ["no_proxy"] = "127.0.0.1,localhost," + os.environ.get("no_proxy", "")
os.environ["NO_PROXY"] = "127.0.0.1,localhost," + os.environ.get("NO_PROXY", "")

import socket, struct, time, json, sys, threading
import xrobotoolkit_sdk as xrt

TCP_CLIENT_MSG_HEAD_CODE = 0x3F
TCP_CLIENT_MSG_TAIL_CODE = 0xA5
TCP_CLIENT_MSG_CONNECT        = 0x19
TCP_CLIENT_MSG_DEVICE_STATE_JSON = 0x6D

def make_msg(cmd, body):
    body_bytes = body.encode('utf-8') if isinstance(body, str) else body
    # TCPMsgHead: head(1) cmd(1) length(4) = 6 bytes, little-endian
    header = struct.pack('<BBL', TCP_CLIENT_MSG_HEAD_CODE, cmd, len(body_bytes))
    # TCPMsgTail: timeStamp(8) tail(1) = 9 bytes, little-endian
    tail = struct.pack('<QB', int(time.time()), TCP_CLIENT_MSG_TAIL_CODE)
    return header + body_bytes + tail

def build_body_json():
    inner = {
        "timeStampNs": time.time_ns(),
        "Controller": {
            "left":  {"pose": "0,0,0,0,0,0,1", "trigger": 0.0, "grip": 0.0,
                      "menuButton": False, "axisX": 0.0, "axisY": 0.0,
                      "axisClick": False, "primaryButton": False, "secondaryButton": False},
            "right": {"pose": "0,0,0,0,0,0,1", "trigger": 0.0, "grip": 0.0,
                      "menuButton": False, "axisX": 0.0, "axisY": 0.0,
                      "axisClick": False, "primaryButton": False, "secondaryButton": False},
        },
        "Head": {"pose": "0,0,1,0,0,0,1"},
        "Hand": {
            "leftHand":  {"scale": 1.0, "isActive": 0, "HandJointLocations": [{"p": "0,0,0,0,0,0,1"} for _ in range(26)]},
            "rightHand": {"scale": 1.0, "isActive": 0, "HandJointLocations": [{"p": "0,0,0,0,0,0,1"} for _ in range(26)]},
        },
        "Body": {
            "timeStampNs": time.time_ns(),
            "joints": [
                {"p": f"{i*0.01:.4f},0,0,0,0,0,1",
                 "va": "0,0,0,0,0,0",
                 "wva": "0,0,0,0,0,0",
                 "t": time.time_ns()}
                for i in range(24)
            ]
        },
    }
    outer = {"value": json.dumps(inner)}
    return json.dumps(outer)

print("[mock] initializing SDK...")
xrt.init()
time.sleep(1)

print(f"[sdk]  before: body={xrt.is_body_data_available()}, motion={xrt.num_motion_data_available()}")

print("[mock] connecting to service on 127.0.0.1:63901...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', 63901))
except Exception as e:
    print(f"[mock] CONNECT FAILED: {e}")
    xrt.close()
    sys.exit(1)

# Send CONNECT message
connect_msg = make_msg(TCP_CLIENT_MSG_CONNECT, "MockDevice|0")
s.sendall(connect_msg)
print(f"[mock] sent CONNECT ({len(connect_msg)} bytes)")
time.sleep(0.5)

# Send body state JSON (3 times, 0.5s apart)
for i in range(5):
    body_json = build_body_json()
    state_msg = make_msg(TCP_CLIENT_MSG_DEVICE_STATE_JSON, body_json)
    s.sendall(state_msg)
    print(f"[mock] sent STATE_JSON #{i+1} ({len(state_msg)} bytes)")
    time.sleep(0.3)
    b = xrt.is_body_data_available()
    m = xrt.num_motion_data_available()
    print(f"[sdk]  body={b}, motion={m}")
    if b:
        print("[sdk]  SUCCESS! Body data received!")
        break

s.close()
print("[mock] disconnected")
print(f"[sdk]  final: body={xrt.is_body_data_available()}")
xrt.close()
