# SONIC 排障记录：`is_body_data_available()` 永远返回 False

> **平台**：Jetson Orin NX（aarch64）  
> **软件**：GR00T-WholeBodyControl，XRoboToolkit SDK，RoboticsServiceProcess  
> **症状**：`xrt.is_body_data_available()` 始终返回 `False`；  
> `pico_manager_thread_server.py --manager` 持续打印 `waiting for body data...`  
> **根因**：系统 HTTP 代理拦截了 gRPC 对 localhost 的连接  
> **修复**：在调用 `xrt.init()` 前设置 `no_proxy=127.0.0.1,localhost`

---

## 一、系统架构

理解问题必须先清楚数据流的三个层次：

```
PICO 头盔 (10.20.1.199)
    │  TCP 63901   ← 全身追踪 JSON，约 60-100 Hz
    ▼
RoboticsServiceProcess   (/opt/apps/roboticsservice/)
    │  gRPC 60061  ← 本地回环，流式推送 ServerFeedback
    ▼
libPXREARobotSDK.so   (Python 绑定 xrobotoolkit_sdk)
    │  回调 OnPXREAClientCallback
    ▼
py_bindings.cpp  解析 JSON → Body.joints → BodyDataAvailable = true
    │
    ▼
xrt.is_body_data_available()  → True ✅
```

**第一层（TCP）**：PICO 设备通过 WiFi 连接到 Jetson 的 63901 端口，发送追踪数据。  
**第二层（gRPC）**：服务进程通过 gRPC 流将数据推送给 SDK，走本地回环 127.0.0.1:60061。  
**第三层（JSON 解析）**：SDK 回调解析 JSON，找到 `Body.joints` 后设置 `BodyDataAvailable = true`。

---

## 二、排查过程（完整复盘）

### 阶段一：确认 PICO 到服务的 TCP 链路正常

```bash
# 确认 PICO TCP 连接存在
ss -tnp | grep 63901
```

输出：
```
ESTAB  0  0  [::ffff:10.20.2.77]:63901  [::ffff:10.20.1.199]:33926
```

PICO 连接状态为 ESTAB，说明 TCP 连接没问题。

服务日志（`/home/unitree/.local/share/PICOBusinessSuitData/log/YYYYMMDD.txt`）也确认设备已注册：

```
new tcp connect device: TestDevice
```

**结论：第一层（TCP）正常。**

---

### 阶段二：确认 PICO 数据在持续传输

服务日志频繁出现：

```
NoPadding data size less than msg: "629"
NoPadding data size less than msg: "763"
```

这是 TCP 分片重组状态机（`tcpconnectionmodel.cpp`）的正常日志。WiFi 上大包被拆分，第一片到达时触发此日志，等待后续片段拼齐。说明 PICO 持续发送数据，**服务进程能收到**。

**结论：第一层数据流通畅。**

---

### 阶段三：排除 PICO 数据格式问题——构造 Mock 注入测试

为了排除"PICO 发的 JSON 格式不对"这一可能，编写了 `test_mock_pico.py`：在本地以正确的 TCP 消息格式（Header 6B + Body + Tail 9B）发送一个完整的全身追踪 JSON（含 24 个 `Body.joints` 字段，共 4907 字节）。

```python
# TCP 消息封装格式（与 Manage_global.h 定义一致）
def make_msg(cmd, body):
    body_bytes = body.encode('utf-8')
    header = struct.pack('<BBL', 0x3F, cmd, len(body_bytes))   # head + cmd + length
    tail   = struct.pack('<QB',  int(time.time()), 0xA5)        # timestamp + tail
    return header + body_bytes + tail

# 发送完整 Body JSON
inner = {"Body": {"joints": [{"p": "..."} for _ in range(24)]}, ...}
outer = {"value": json.dumps(inner)}   # 双层 JSON（PICO 实际格式）
state_msg = make_msg(0x6D, json.dumps(outer))  # 4907 字节，本地回环不会分片
s.sendall(state_msg)
```

**结果：所有 5 次发送，SDK 均返回 `body=False`。**

服务日志中也没有出现 "MockDevice" 相关的记录，说明数据从未到达 SDK。

**关键推论：问题出在第二层（gRPC），而非数据格式。**

---

### 阶段四：确认 gRPC 流从未建立

gRPC 订阅流由 `WatchServerFeedback` 方法建立，服务侧在被调用时会打印：

```
server start feedback of pid XXXXX
```

全量搜索日志：

```bash
grep "server start feedback\|add pid" \
  /home/unitree/.local/share/PICOBusinessSuitData/log/20260620.txt
```

**输出为空。** 整个日志文件中，`WatchServerFeedback` 从未被调用。

SDK 内部（`PXREARobotSDK.cpp`）的逻辑：

```cpp
void StartServiceCheck() {
    m_checkThread = std::thread([this] {
        bool connect = false;
        while (m_bChecking) {
            if (SendBeat()) {          // ← 心跳 RPC（500ms 超时）
                sleep(500ms);
                if (!connect) {
                    WatchServerFeedback();  // ← 只有心跳成功后才建立数据流
                    connect = true;
                }
            }
            // 心跳失败 → 不调用 WatchServerFeedback，继续重试
        }
    });
}
```

`SendBeat()` 若始终失败，`WatchServerFeedback()` 永远不会被调用，所有回调永远不会触发，`is_body_data_available()` 永远返回 `False`。

**结论：gRPC 心跳（SendBeat）失败，第二层断路。**

---

### 阶段五：诊断 gRPC 连接为何失败

开启 gRPC 连接追踪日志：

```bash
SDK_DIR="/home/unitree/Humanoid/GR00T-WholeBodyControl/external_dependencies/XRoboToolkit-PC-Service-Pybind_X86_and_ARM64"
cd "$SDK_DIR"
GRPC_VERBOSITY=DEBUG GRPC_TRACE=connectivity_state,subchannel \
LD_LIBRARY_PATH="$PWD/lib/aarch64:$LD_LIBRARY_PATH" PYTHONPATH="$PWD" \
/home/unitree/.local/bin/python3.10 -c "
import xrobotoolkit_sdk as xrt
import time
xrt.init()
time.sleep(3)
xrt.close()
" 2>&1 | grep -E "proxy|CONNECTING|READY|connect"
```

关键输出（节选）：

```
ConnectivityStateTracker client_channel: IDLE -> CONNECTING (started resolving, OK)

http_connect_handshaker.cc:299] Connecting to server 127.0.0.1:60061
    via HTTP proxy ipv4:192.168.123.100:7897          ← !!!

ConnectivityStateTracker client_channel: CONNECTING -> SHUTDOWN
```

**根因找到：gRPC 正在把对 `127.0.0.1:60061`（本地 gRPC 服务）的连接，通过系统 HTTP 代理 `192.168.123.100:7897` 来路由！**

代理无法转发本地回环地址，连接永远停留在 `CONNECTING` 状态，500ms 后 `SendBeat()` 以 `DEADLINE_EXCEEDED` 失败。

同时确认了端口 60061 本身没问题——直接发 HTTP/2 握手帧是有响应的：

```python
import socket
s = socket.socket(); s.connect(('127.0.0.1', 60061))
s.sendall(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n' + b'\x00\x00\x00\x04\x00\x00\x00\x00\x00')
print(s.recv(4096).hex())  # 服务正常返回 SETTINGS 帧
```

**结论：服务进程正常，只是 gRPC 客户端走了代理。**

---

## 三、根本原因

### 环境变量

```bash
$ env | grep -i proxy
http_proxy=http://192.168.123.100:7897
HTTP_PROXY=http://192.168.123.100:7897
https_proxy=http://192.168.123.100:7897
HTTPS_PROXY=http://192.168.123.100:7897
no_proxy=        ← 空！
NO_PROXY=        ← 空！
```

系统为了访问外网设置了 HTTP 代理，但 `no_proxy` 未排除 `127.0.0.1` 和 `localhost`。

### 为什么 gRPC 会走代理？

gRPC C++ 库（libPXREARobotSDK.so 静态链接）实现了标准的代理发现机制：  
启动时读取 `http_proxy` / `HTTP_PROXY` 环境变量，对所有 TCP 连接发送 `CONNECT` 代理请求——  
**包括对 127.0.0.1 的本地回环连接。**

这与大多数 HTTP 库（如 curl、wget）的行为相同：如果 `no_proxy` 为空，代理规则对所有地址生效。

### 完整故障链

```
xrt.init()
  └─ PXREAInit()
       └─ grpc::CreateCustomChannel("127.0.0.1:60061")
            └─ 读取 http_proxy=192.168.123.100:7897，no_proxy=""
                 └─ 向代理发送 CONNECT 127.0.0.1:60061
                      └─ 代理拒绝或无响应（不支持转发 127.0.0.1）
                           └─ gRPC 信道卡在 CONNECTING，等到 500ms deadline
                                └─ SendBeat() → DEADLINE_EXCEEDED
                                     └─ WatchServerFeedback() 永远不被调用
                                          └─ OnPXREAClientCallback 从不触发
                                               └─ BodyDataAvailable 永远 = false
                                                    └─ is_body_data_available() → False ❌
```

---

## 四、修复方案

### 方法（已应用）

在所有调用 `xrt.init()` 的 Python 脚本**顶部**，**在任何 import 之前**，手动将本地地址加入 `no_proxy`：

```python
import os
# 绕过 HTTP 代理，使 gRPC 直连本地 XRoboToolkit 服务（127.0.0.1:60061）
# 若不设置，系统代理会拦截所有 localhost 连接，导致 gRPC 卡在 CONNECTING 状态
os.environ["no_proxy"] = "127.0.0.1,localhost," + os.environ.get("no_proxy", "")
os.environ["NO_PROXY"] = "127.0.0.1,localhost," + os.environ.get("NO_PROXY", "")
```

### 已修改的文件

| 文件 | 修改位置 |
|------|----------|
| `gear_sonic/scripts/pico_manager_thread_server.py` | 第 31–32 行（`from collections import...` 之后） |
| `test_mock_pico.py` | 第 5–6 行（`import socket...` 之前） |

### 为什么必须在 import 前设置？

gRPC 在 `grpc::CreateCustomChannel()` 被调用时读取代理环境变量，时机是 `xrt.init()` 内部。只要 `os.environ` 在 `xrt.init()` 之前修改即可。`import xrobotoolkit_sdk` 本身不初始化 gRPC 信道，所以 import 后、init 前设置也可以，但写在最顶部最安全。

### 可选的系统级永久修复

如果不想在每个脚本里都写这几行，也可以在 `~/.bashrc` 中永久排除本地地址：

```bash
# 追加到 ~/.bashrc
export no_proxy="127.0.0.1,localhost,${no_proxy}"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY}"
```

---

## 五、修复验证

### Mock 注入测试（端到端验证）

```bash
SDK_DIR="/home/unitree/Humanoid/GR00T-WholeBodyControl/external_dependencies/XRoboToolkit-PC-Service-Pybind_X86_and_ARM64"
cd "$SDK_DIR"
LD_LIBRARY_PATH="$PWD/lib/aarch64:$LD_LIBRARY_PATH" PYTHONPATH="$PWD" \
/home/unitree/.local/bin/python3.10 \
  /home/unitree/Humanoid/GR00T-WholeBodyControl/test_mock_pico.py
```

预期输出：

```
initialize sdk,connect127.0.0.1:60061
client start server stream
server connect                         ← gRPC 信道建立 ✅
watch server feedback thread start     ← WatchServerFeedback 被调用 ✅
device find TestDevice

[mock] sent STATE_JSON #1 (4907 bytes)
[sdk]  body=True, motion=0             ← SDK 成功解析 Body 数据 ✅
[sdk]  SUCCESS! Body data received!
```

### 真机 PICO Manager 验证

```bash
cd /home/unitree/Humanoid/GR00T-WholeBodyControl
python gear_sonic/scripts/pico_manager_thread_server.py --manager
```

预期输出（确认 PICO 处于 Full Body 模式后）：

```
TestDevice
[Manager] ZMQ socket bound to port 5556
[PicoReader] dt_ts: 13.76 ms, fps: 72.07   ← 72 Hz 全身追踪 ✅
[PicoReader] dt_ts: 13.81 ms, fps: 72.21
```

---

## 六、PICO 端配置要求

即使 gRPC 修复后，若 `is_body_data_available()` 仍为 False，说明 PICO 未发送 Body 数据。检查方法：看服务日志中 NoPadding 的数据包大小，Full Body 模式下每包约 5000–9000 字节；若全部 < 1000 字节，说明 PICO 只在发送 Controller/Head 数据。

**PICO 头盔必须满足以下条件：**

1. 打开 **XRoboToolkit** 应用（不是普通的 PICO 主界面）
2. 设置 **"Pico Motion Tracker"** → **"Full body"**（需要 Pico Swift 动作捕捉器）
3. 设置 **"Data/Control"** → **"Send"**
4. 确认 **Pico Swift 动捕设备**已开机并与头盔配对连接
5. 保持头盔活跃状态（屏幕不休眠）

---

## 七、诊断速查

遇到 `body=False` 时，按以下顺序快速定位：

### 第一步：检查代理

```bash
env | grep -i proxy
```

若 `no_proxy` 不含 `127.0.0.1`，则代理是根因，参见第四节修复。

### 第二步：确认 gRPC 是否直连（不走代理）

```bash
SDK_DIR="/home/unitree/Humanoid/GR00T-WholeBodyControl/external_dependencies/XRoboToolkit-PC-Service-Pybind_X86_and_ARM64"
cd "$SDK_DIR"
GRPC_VERBOSITY=DEBUG GRPC_TRACE=connectivity_state \
LD_LIBRARY_PATH="$PWD/lib/aarch64:$LD_LIBRARY_PATH" PYTHONPATH="$PWD" \
no_proxy="127.0.0.1,localhost" NO_PROXY="127.0.0.1,localhost" \
/home/unitree/.local/bin/python3.10 -c "
import xrobotoolkit_sdk as xrt; import time
xrt.init(); time.sleep(3); xrt.close()
" 2>&1 | grep -E "proxy|READY|CONNECTING|server connect"
```

正常（修复后）应看到：
```
server connect          ← 无 proxy 字样，gRPC 直连成功
```

异常（代理问题）会看到：
```
via HTTP proxy ipv4:192.168.123.100:7897   ← 还在走代理
```

### 第三步：确认 WatchServerFeedback 是否被调用

```bash
grep "server start feedback" \
  /home/unitree/.local/share/PICOBusinessSuitData/log/$(date +%Y%m%d).txt
```

若无输出 → gRPC 未连上；若有输出 → gRPC 正常，问题在 PICO 数据。

### 第四步：运行 Mock 注入测试

```bash
# 验证整条管线（排除 PICO 因素）
cd external_dependencies/XRoboToolkit-PC-Service-Pybind_X86_and_ARM64
LD_LIBRARY_PATH="$PWD/lib/aarch64:$LD_LIBRARY_PATH" PYTHONPATH="$PWD" \
/home/unitree/.local/bin/python3.10 \
  /home/unitree/Humanoid/GR00T-WholeBodyControl/test_mock_pico.py
```

若 Mock 测试 `body=True` 但真实 PICO 仍 `False` → PICO 未开 Full Body 模式。

### 第五步：检查 PICO 数据包大小

```bash
grep "NoPadding" \
  /home/unitree/.local/share/PICOBusinessSuitData/log/$(date +%Y%m%d).txt \
  | awk '{print $NF}' | sort -n | tail -5
```

- 数值 > 1000（如 3000+）→ PICO 在发大包 → Full Body 数据存在，排查 JSON 解析
- 数值均 < 1000 → PICO 只发小包 → 确认 Full Body 模式未开启

---

## 八、注意事项

### SDK 只支持 Python 3.10

```
xrobotoolkit_sdk.cpython-310-aarch64-linux-gnu.so
```

Jetson 上系统默认 `python3` 指向 Anaconda 的 3.13，必须使用：

```bash
/home/unitree/.local/bin/python3.10
```

`pico_manager_thread_server.py` 在 `.venv_teleop` 环境中运行，该环境已配置 Python 3.10，可正常使用。

### 退出时的 `terminate called without an active exception`

`xrt.close()` 析构时，`libPXREARobotSDK.so` 内部的 `~PXREAClient()` 存在线程清理竞争，可能在控制台打印此警告。这不影响功能，属于 SDK 的已知问题，忽略即可。
