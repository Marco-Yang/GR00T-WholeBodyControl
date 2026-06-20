# SONIC 启动指南

> 本文档面向已完成环境配置的用户，说明以下两种场景的完整启动流程：
>
> - **场景一：PICO 遥操 + MuJoCo 仿真**（三个终端，仿真验证）
> - **场景二：PICO 遥操 + G1 真机**（两个终端，真实部署）
>
> 前置要求：已按 `SONIC_环境配置指南.md` 完成环境安装与模型下载。

---

## 场景一：PICO 遥操 + MuJoCo 仿真

### 数据流

```
Terminal 3: PICO Manager (ZMQ:5556)
       ↑  xrobotoolkit
  PICO VR（WiFi）
       ↓
Terminal 2: C++ 部署程序 (deploy.sh sim)  ←──DDS──→  Terminal 1: MuJoCo 仿真器
```

### 启动步骤

> **顺序很重要**：先启 MuJoCo → 再启 deploy → 再启 PICO Manager

---

**Terminal 1 — MuJoCo 仿真器**

```bash
cd ~/Humanoid/GR00T-WholeBodyControl
source .venv_sim/bin/activate
python gear_sonic/scripts/run_sim_loop.py
```

等待 MuJoCo 窗口出现，机器人处于初始站立姿态后，继续下一步。

---

**Terminal 2 — C++ 部署程序（Sim 模式）**

```bash
cd ~/Humanoid/GR00T-WholeBodyControl/gear_sonic_deploy
bash deploy.sh sim
```

出现以下提示表示 DDS 就绪，等待 PICO Manager 连接：

```
Init Done
```

---

**Terminal 3 — PICO Manager（遥操控制端）**

```bash
cd ~/Humanoid/GR00T-WholeBodyControl
source .venv_teleop/bin/activate

# 标准启动（含 VR 3点可视化）
python gear_sonic/scripts/pico_manager_thread_server.py --manager \
    --vis_vr3pt --vis_smpl

# 简洁启动（低延迟，推荐调试）
python gear_sonic/scripts/pico_manager_thread_server.py --manager
```

等待输出：

```
[Manager] ZMQ socket bound to port 5556
Manager controls: A+X=toggle mode, A+B+X+Y=start/stop policy
```

---

### PICO 头显操作顺序

| 步骤 | 操作 |
|------|------|
| 1 | 打开 PICO 上的 XRoboToolkit App |
| 2 | 输入 NX 的 **WiFi IP**（如 `10.20.2.77`）并连接 |
| 3 | 连接状态显示 **WORKING** |
| 4 | 戴上 PICO，进行身体姿态校准 |
| 5 | 戴上脚踝追踪器，用 PICO 看向追踪器，等待图标变绿 |
| 6 | Terminal 3 停止打印 `waiting for body data...`，开始正常输出 |

---

### 控制流程

| 步骤 | 按键 | 位置 | 说明 |
|------|------|------|------|
| 1 | MuJoCo 窗口按 `9` | Terminal 1 | 开启弹性辅助力，机器人站稳 |
| 2 | PICO 按 `A+B+X+Y` | PICO 控制器 | 启动 policy，进入 PLANNER 模式 |
| 3 | PICO 推左摇杆 | PICO 控制器 | 控制行走方向 |
| 4 | PICO 推右摇杆 X 轴 | PICO 控制器 | 调整朝向（左/右转） |
| 5 | 长按 `A` / `X` | PICO 控制器 | **右手/左手 夹爪缓慢闭合** |
| 6 | 长按 `B` / `Y` | PICO 控制器 | **右手/左手 夹爪缓慢张开** |
| 7 | 捏住左/右 Trigger | PICO 控制器 | **冻结对应夹爪**（保持当前位置） |
| 8 | PICO 按 `A+B+X+Y` | PICO 控制器 | 停止 policy，退出 |

---

## 场景二：PICO 遥操 + G1 真机

### 数据流

```
Terminal 2: PICO Manager (ZMQ:5556)
       ↑  xrobotoolkit
  PICO VR（WiFi）
       ↓
Terminal 1: C++ 部署程序 (deploy.sh real) ──DDS──→ G1 机器人
```

### 网络要求

| 设备 | 连接方式 | IP 示例 |
|------|----------|---------|
| Jetson Orin NX | WiFi（与 PICO 同局域网） | `10.20.2.77` |
| PICO VR 头显 | WiFi（与 NX 同局域网） | `10.20.1.199` |
| G1 机器人 | 网线连接 NX | `192.168.123.x` |

> **注意**：NX 必须同时连接 WiFi（与 PICO 通信）和网线（与 G1 通信），两个网络互相独立。

### 启动步骤

**Terminal 1 — C++ 部署程序（真机模式）**

```bash
cd ~/Humanoid/GR00T-WholeBodyControl/gear_sonic_deploy

# 自动检测 192.168.123.x 机器人网卡
bash deploy.sh real

# 或指定网卡名
bash deploy.sh enP8p1s0
```

出现 `Init Done` 提示后，继续下一步。

---

**Terminal 2 — PICO Manager（遥操控制端）**

```bash
cd ~/Humanoid/GR00T-WholeBodyControl
source .venv_teleop/bin/activate

python gear_sonic/scripts/pico_manager_thread_server.py --manager
```

等待输出 `[Manager] ZMQ socket bound to port 5556`。

---

### PICO 头显操作顺序

与场景一相同（见上方表格）。

---

### 控制流程

| 步骤 | 按键 | 说明 |
|------|------|------|
| 1 | PICO 按 `A+B+X+Y` | 启动 policy，进入 PLANNER 模式 |
| 2 | PICO 推左摇杆 | 控制行走方向 |
| 3 | PICO 推右摇杆 X 轴 | 调整朝向 |
| 4 | 长按 `A` / `X` | 右手/左手 夹爪缓慢闭合 |
| 5 | 长按 `B` / `Y` | 右手/左手 夹爪缓慢张开 |
| 6 | 捏住左/右 Trigger | 冻结对应夹爪（保持当前位置） |
| 7 | PICO 按 `A+B+X+Y` | 停止 policy |

---

## PICO 控制器完整按键说明

### 模式状态机

```
         OFF
          │
      A+B+X+Y
          ↓
       PLANNER  ←──A+X──→  POSE
          │                   │
          │               A/X/B/Y = 夹爪控制
          │               Trigger = 冻结夹爪
          │
        B+Y（从 POSE 进入）
          ↓
  PLANNER_FROZEN_UPPER_BODY
          │
    L-Stick Click
          ↓
    PLANNER_VR_3PT
          │
    L-Stick Click
          ↓
  （返回 PLANNER_FROZEN）

任意模式 + A+B+X+Y → OFF（停止）
```

### 按键速查表

#### 模式切换

| 按键组合 | 当前模式 | 切换到 |
|----------|----------|--------|
| `A+B+X+Y` | OFF | PLANNER（启动） |
| `A+B+X+Y` | 任意激活模式 | OFF（停止） |
| `A+X` | PLANNER | POSE |
| `A+X` | POSE | PLANNER |
| `B+Y` | POSE | PLANNER_FROZEN_UPPER_BODY |
| `B+Y` | PLANNER_FROZEN | POSE |
| `L-Stick Click` | PLANNER_FROZEN | → PLANNER_VR_3PT |
| `L-Stick Click` | PLANNER_VR_3PT | 返回 PLANNER_FROZEN |

#### PLANNER 模式运动控制

| 按键 | 功能 |
|------|------|
| 左摇杆（LX / LY） | 行走方向（前后左右） |
| 右摇杆 X 轴（RX） | 朝向（左转 / 右转） |
| `A+B`（同时） | 切换到下一个运动模式 |
| `X+Y`（同时） | 切换到上一个运动模式 |
| 左 Menu 键（长按） | 进入 POSE_PAUSE（暂停姿态流） |

#### 夹爪控制（POSE / PLANNER_VR_3PT 模式有效）

| 按键 | 手 | 动作 |
|------|----|------|
| 长按 `A` | 右手 | 缓慢闭合 |
| 长按 `B` | 右手 | 缓慢张开 |
| 长按 `X` | 左手 | 缓慢闭合 |
| 长按 `Y` | 左手 | 缓慢张开 |
| 捏住右 Trigger | 右手 | 冻结当前位置 |
| 捏住左 Trigger | 左手 | 冻结当前位置 |

> **注意**：进入 POSE 模式时需同时按 A+X，松开后夹爪才开始响应，避免误触发。

| 状态 | 关节位置（rad）|
|------|----------------|
| **张开**（初始） | 全零 `[0, 0, 0, 0, 0, 0, 0]` |
| **夹紧** | 左手 `[0, 0.7, 0.7, -1.0, -1.5, -1.0, -1.5]` |
| **夹紧** | 右手 `[0, -0.7, -0.7, 1.0, 1.5, 1.0, 1.5]` |

---

## 紧急停止

| 优先级 | 操作 | 效果 |
|--------|------|------|
| 1（最高） | PICO 按 `A+B+X+Y` | 发 stop 命令，Terminal 2/3 退出 |
| 2 | Terminal 1 按 `O` | C++ deploy 停止发命令 |
| 3（保底） | G1 遥控器 `L2+A` | 机器人进入阻尼模式 |

---

## 常见问题

**Q: PICO Manager 输出一直打印 `waiting for body data...`？**

1. 确认 PICO 和 NX 在同一 WiFi 网络
2. 确认 XRoboToolkit App 连接状态为 **WORKING**
3. 检查代理设置（排除对 localhost 的代理）：
   ```bash
   export no_proxy="localhost,127.0.0.1"
   unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
   ```

**Q: deploy.sh 启动后 C++ 程序提示文件缺失？**

```bash
# 下载模型文件（在 GR00T-WholeBodyControl 根目录）
unset HF_ENDPOINT
python download_from_hf.py
```

**Q: MuJoCo 场景一中机器人没有响应 PICO？**

确认三个终端的启动顺序：MuJoCo → deploy sim → PICO Manager。
如果 deploy 先于 MuJoCo 启动，DDS 可能绑定失败，重启 Terminal 2。

---

## 快速参考卡

```
场景一（PICO + MuJoCo）：
  T1: source .venv_sim/bin/activate
      python gear_sonic/scripts/run_sim_loop.py
  T2: cd gear_sonic_deploy && bash deploy.sh sim
  T3: source .venv_teleop/bin/activate
      python gear_sonic/scripts/pico_manager_thread_server.py --manager
  MuJoCo 窗口：9=弹簧  Backspace=重置

场景二（PICO + G1 真机）：
  T1: cd gear_sonic_deploy && bash deploy.sh real
  T2: source .venv_teleop/bin/activate
      python gear_sonic/scripts/pico_manager_thread_server.py --manager

PICO 通用按键：
  A+B+X+Y = 启动/停止 policy
  A+X     = PLANNER ↔ POSE
  B+Y     = POSE ↔ FROZEN（VR全身控制入口）
  A/X     = 右手/左手夹爪闭合（松开 A+X 后生效）
  B/Y     = 右手/左手夹爪张开
  Trigger = 冻结对应夹爪
```
