# PICO VR 全身遥操保姆级指南

> 前提：已完成 sim2sim（MuJoCo 仿真验证通过）。
> 本文档从零开始，覆盖 PICO 硬件配置 → 软件安装 → 网络连接 → Sim 遥操验证 → 真机部署全流程。

---

## 目录

1. [系统架构说明](#1-系统架构说明)
2. [所需硬件](#2-所需硬件)
3. [Step 1：安装 XRoboToolkit PC 服务（电脑端）](#3-step-1安装-xrobotoolkit-pc-服务电脑端)
4. [Step 2：PICO 头显安装 XRoboToolkit App](#4-step-2pico-头显安装-xrobotoolkit-app)
5. [Step 3：脚踝动捕器配置与校准](#5-step-3脚踝动捕器配置与校准)
6. [Step 4：安装 Python 遥操环境](#6-step-4安装-python-遥操环境)
7. [Step 5：网络连接（PICO ↔ 电脑）](#7-step-5网络连接pico--电脑)
8. [Step 6：Sim 遥操验证（先在仿真里练）](#8-step-6sim-遥操验证先在仿真里练)
9. [Step 7：真机 G1 遥操部署（笔记本版）](#9-step-7真机-g1-遥操部署笔记本版)
10. [Step 8：NX 板载真机 G1 遥操部署](#10-step-8nx-板载真机-g1-遥操部署)
11. [PICO 按键完整速查](#11-pico-按键完整速查)
12. [校准姿态与模式切换安全规范](#12-校准姿态与模式切换安全规范)
13. [Unitree SDK2 与部署代码的桥接原理](#13-unitree-sdk2-与部署代码的桥接原理)
14. [常见问题排查](#14-常见问题排查)

---

## 1. 系统架构说明

理解整体数据流，有助于定位问题：

```
[PICO 头显 + 控制器 + 脚踝动捕器]
         │ 全身姿态数据（Wi-Fi）
         ▼
[XRoboToolkit PC Service]（电脑后台进程）
         │ 内部协议
         ▼
[pico_manager_thread_server.py]（Python，.venv_teleop）
    → 将 PICO 体态转换为 SMPL 姿态
    → 通过 ZMQ（端口 5556）发布 pose 数据
         │ ZMQ / DDS（loopback 或网络）
         ▼
[g1_deploy_onnx_ref]（C++ 二进制，--input-type zmq_manager）
    → SONIC policy 推理（ONNX / TensorRT）
    → 输出关节力矩目标
         │ Unitree SDK2 DDS（CycloneDDS）
         ▼
[MuJoCo 仿真器（sim）] 或 [真机 G1（real，192.168.123.x）]
```

**关键角色：**

| 组件                                   | 语言      | 作用                                                                 |
| -------------------------------------- | --------- | -------------------------------------------------------------------- |
| `XRoboToolkit PC Service`            | 系统服务  | 接收 PICO 体态数据，暴露给本地 SDK                                   |
| `pico_manager_thread_server.py`      | Python    | 读取 XRoboToolkit SDK → 转 SMPL → ZMQ 发布                         |
| `deploy.sh --input-type zmq_manager` | C++       | 订阅 ZMQ → SONIC 推理 → Unitree SDK2 下发命令                      |
| `unitree_sdk2`                       | C++ / DDS | 与 G1 机器人通信的底层 SDK（sim 用 loopback，real 用 192.168.123.x） |
| `run_sim_loop.py`                    | Python    | MuJoCo 仿真器，订阅同一 DDS 域，只在 sim 时用                        |

---

## 2. 所需硬件

| 硬件            | 型号                                | 说明                       |
| --------------- | ----------------------------------- | -------------------------- |
| VR 头显         | **PICO 4 / PICO 4 Pro**       | 必须，头部 + 手部追踪      |
| VR 控制器       | PICO 4 自带 2 个                    | 必须                       |
| 脚踝动捕器      | **PICO Motion Tracker × 2**  | 必须，绑在脚踝             |
| Wi-Fi 路由器    | 低延迟私用路由器（推荐 5GHz）       | 必须，不要用公共 / 校园网  |
| 工作站 / 笔记本 | Ubuntu 22.04 / 24.04，有 NVIDIA GPU | 运行 deploy 和 teleop 脚本 |

> **Wi-Fi 延迟要求：** < 10ms 为佳，< 30ms 可接受，> 30ms 会导致机器人动作不稳定。

---

## 3. Step 1：安装 XRoboToolkit PC 服务（电脑端）

PC Service 是在电脑后台运行的系统服务，PICO 头显通过 Wi-Fi 连接它来传输体态数据。**必须先装好再启动 PICO App。**

**Ubuntu 22.04（x86_64）：**

```bash
wget https://github.com/XR-Robotics/XRoboToolkit-PC-Service/releases/download/v1.0.0/XRoboToolkit_PC_Service_1.0.0_ubuntu_22.04_amd64.deb
sudo dpkg -i XRoboToolkit_PC_Service_1.0.0_ubuntu_22.04_amd64.deb
```

**Ubuntu 24.04（x86_64）：**

```bash
wget https://github.com/XR-Robotics/XRoboToolkit-PC-Service/releases/download/v1.0.0/XRoboToolkit_PC_Service_1.0.0_ubuntu_24.04_amd64.deb
sudo dpkg -i XRoboToolkit_PC_Service_1.0.0_ubuntu_24.04_amd64.deb
```

**G1 机载 Jetson Orin NX（aarch64）：**

```bash
# 安装包已随仓库附带
sudo dpkg -i gear_sonic_deploy/thirdparty/roboticsservice_1.0.0.0_arm64.deb
```

其他平台版本：https://github.com/XR-Robotics/XRoboToolkit-PC-Service/releases

安装后服务会**自动后台运行**，无需手动启动。

---

## 4. Step 2：PICO 头显安装 XRoboToolkit App

以下操作全部在 **头显内** 进行：

1. 戴上 PICO 头显，按指引完成初始设置
2. 进入 Wi-Fi 设置，连接与电脑**同一个**路由器（重要）
3. 开启 Developer Mode：**设置 → 开发者 → 开发者模式 → 开启**
4. 打开 PICO 内置**浏览器**应用
5. 搜索栏输入 `xrobotoolkit`，进入 GitHub 页面
6. 直接下载 APK（或在浏览器输入下载链接）：

   ```
   https://github.com/XR-Robotics/XRoboToolkit-Unity-Client/releases/download/v1.1.1/XRoboToolkit-PICO-1.1.1.apk
   ```
7. 点击浏览器右上角"下载管理"，找到已下载的 APK，点击安装
8. 安装完成后，App 出现在资源库的 **"Unknown"（未知来源）** 分类中

> 其他版本：https://github.com/XR-Robotics/XRoboToolkit-Unity-Client/releases

---

## 5. Step 3：脚踝动捕器配置与校准

### 5.1 绑定动捕器

1. 将两个 PICO Motion Tracker 分别绑到**左脚踝**和**右脚踝**
2. **有指示灯的一面朝上**
3. 如果穿宽松裤子，将裤腿向上卷，确保动捕器对 PICO 相机**清晰可见**（追踪靠视觉）

### 5.2 PICO 端配对动捕器

在 PICO 头显内操作：

1. 进入 **设置 → 开发者**，将 **"Safeguard"（安全边界）** 关闭
2. 点击 PICO 菜单中的 **Wi-Fi 图标**，会显示头显的示意图
3. 头显图标上方有两个小圆圈图标 = 动捕器。若没有，先打开 **Motion Tracker App**
4. 点击每个动捕器旁边的 **"i"** 图标，选择 **"取消配对"**（清除旧配对）
5. 清除后点击右上角 **"配对"** 按钮
6. 按住每个动捕器顶部按钮 **6 秒**，直到指示灯**红蓝交替闪烁**（进入配对模式）
7. 两个动捕器依次配对完成

### 5.3 校准动捕器

配对后必须校准，否则脚部追踪会漂移：

1. 戴好 PICO 头显（戴在眼睛上）
2. 点击蓝色 **"Calibrate（校准）"** 按钮，按提示完成两个序列：
   - **序列 1：** 站直，双臂自然垂放，手持控制器静止
   - **序列 2：** 低头看脚部动捕器，直到 PICO 相机识别到它们
3. 校准完成后，将头显**移到额头上方佩戴**（额头式佩戴，确保 PICO 继续朝前检测动捕器）

> **校准不好的后果：** 脚部追踪失效 → 机器人脚步错乱 → 摔倒或危险动作。建议每次遥操开始前重新校准。

---

## 6. Step 4：安装 Python 遥操环境

从仓库根目录运行：

```bash
cd ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl   # 替换为你的路径
bash install_scripts/install_pico.sh
```

脚本自动完成：

- 安装 `uv` 包管理器
- 安装 uv 托管的 Python 3.10（含开发头文件）
- 创建 `.venv_teleop` 虚拟环境
- 安装 `gear_sonic[teleop]`（ZMQ、Pinocchio、PyVista 等）
- 安装 `gear_sonic[sim]`（MuJoCo，x86_64 时）
- 编译安装 XRoboToolkit SDK（CMake 构建）
- 安装 `unitree_sdk2_python` 绑定

激活环境：

```bash
source .venv_teleop/bin/activate
# 提示符变为：(gear_sonic_teleop)
```

> **注意：** 如果同时激活了 conda 环境（如 SONIC）和 .venv_teleop，venv 会覆盖 conda。运行遥操脚本时确保 `python` 指向 `.venv_teleop/bin/python`，可用 `which python` 验证。

---

## 7. Step 5：网络连接（PICO ↔ 电脑）

1. 确保 PICO 和电脑连接到**同一个 Wi-Fi 路由器**
2. 查看电脑的局域网 IP：

   ```bash
   ip -4 addr show | grep inet
   # 找到形如 192.168.x.x 的地址，记下来
   ```
3. 在 PICO 头显内打开 **XRoboToolKit App**
4. 点击 "PC Service:" 旁边的 **"Enter"**，输入电脑的 IP 地址
5. 确认 "Status:" 显示 **"WORKING"**（若已有 IP，点 "Reconnect"）
6. 在 App 内勾选以下选项：

   | 区域                | 选项       | 设置              |
   | ------------------- | ---------- | ----------------- |
   | Tracking            | Head       | ✅ 勾选           |
   | Tracking            | Controller | ✅ 勾选           |
   | Data/Control        |            | 选**"Send"**      |
   | Pico Motion Tracker |            | 选**"Full body"** |
7. 状态正常后，头显内应能看到体态预览（骨架或虚拟人）

---

## 8. Step 6：Sim 遥操验证（先在仿真里练）

> **强烈建议：** 在真机部署之前，在仿真里熟练掌握全部操作流程和紧急停止。

需要**三个终端**同时运行。

### 终端 1 — MuJoCo 仿真器

```bash
cd ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl
source .venv_teleop/bin/activate
python gear_sonic/scripts/run_sim_loop.py
```

等待 MuJoCo 窗口出现，机器人以 T 形姿态悬空显示。

### 终端 2 — C++ 推理程序（zmq_manager 模式）

```bash
cd ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl/gear_sonic_deploy
bash ./deploy.sh --input-type zmq_manager sim
```

等待终端输出 **"Init done"**，表示 DDS 和 ZMQ 均已就绪。

### 终端 3 — PICO 姿态流媒体服务

```bash
cd ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl
source .venv_teleop/bin/activate

# 推荐首次运行加可视化，会弹出 G1 骨架预览窗口
python gear_sonic/scripts/pico_manager_thread_server.py --manager \
    --vis_vr3pt --vis_smpl
```

若弹出 G1 骨架窗口且跟随你的身体运动，说明 PICO 数据正常接入。
若无窗口，检查 XRoboToolKit App 的 IP 配置。

### 遥操操作流程

1. **穿合适的衣物**（见下方安全规范）
2. 运行终端1,在 MuJoCo 窗口按 **`9`** 开启弹性辅助力，机器人自动站稳落地
3. **在PICO中打开体感追踪器APP，站好校准姿态**（见 [第 12 节](#12-校准姿态与模式切换安全规范)）
4. 在终端 2 运行
   cd ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl/gear_sonic_deploybash ./deploy.sh --input-type zmq_manager sim按 **`]`** 启动 policy
5. 在 PICO 控制器上同时按 **A + B + X + Y** → policy 初始化 + 全身校准（CALIB_FULL），机器人进入 **PLANNER** 模式开始平衡
6. 按 **A + X** 进入 **POSE** 模式 → 机器人开始跟随你的全身动作
7. 完成后按 **A + B + X + Y** 紧急停止，机器人回到 OFF 状态

---

## 9. Step 7：真机 G1 遥操部署（笔记本版）

> **警告：** 只有在仿真里操作熟练后才进行真机部署。确保已关闭所有 `run_sim_loop.py` 进程，否则会与真机冲突。

此方案所有代码运行在**笔记本**上，通过网线（192.168.123.x）向 G1 发送电机指令，无需在 G1 内部安装任何软件。真机部署只需**两个终端**（无需 MuJoCo）。

### 前置检查

**① 配置笔记本以太网口 IP（每次重启后需重新执行）：**

```bash
# 查看当前以太网接口名
ip link show | grep -E "^[0-9]+: en"

# 配置静态 IP（替换 enp110s0 为实际接口名）
sudo ip addr add 192.168.123.100/24 dev enp110s0
sudo ip link set enp110s0 up
```

若提示 `Address already assigned` 说明 IP 还在，跳过此步。

**② 确认 G1 网络连通：**

```bash
ping 192.168.123.165
```

**③ 确认 TensorRT 环境变量：**

```bash
echo $TensorRT_ROOT
# 应输出 /home/adam/TensorRT
# 若为空：export TensorRT_ROOT=$HOME/TensorRT
```

### 终端 1 — C++ 推理程序（真机模式）

```bash
cd ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl/gear_sonic_deploy
bash deploy.sh --input-type zmq_manager real

# 若自动检测网口失败，直接传 G1 的 IP
# bash deploy.sh --input-type zmq_manager 192.168.123.164
```

等待 **"Init done"**。

> **注意：** 必须使用 `bash deploy.sh` 而不是 `source scripts/setup_env.sh && ./deploy.sh`。在 zsh 下 source setup_env.sh 会破坏 PATH，导致后续命令找不到。

### 终端 2 — PICO 姿态流媒体服务

```bash
cd ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl
source .venv_teleop/bin/activate
python gear_sonic/scripts/pico_manager_thread_server.py --manager

# 若有外接显示器，可加可视化：
# python gear_sonic/scripts/pico_manager_thread_server.py --manager \
#     --vis_vr3pt --vis_smpl
```

> **多机场景：** 若遥操脚本（终端 2）在不同机器上运行，需在 deploy.sh 加 `--zmq-host <遥操机器的IP>`。

### 真机操作流程

#### 第一阶段：安全与硬件准备

1. **清场**：确保机器人周围 **3 米净空**，无障碍物和无关人员
2. **挂安全绳 / 龙门架**：将 G1 挂上龙门架或安全绳，保持机器人松弛站立（policy 启动后会自主平衡）
3. **安全员就位**：另一人守在终端 1 的键盘旁，手放在 **`O`** 键上，随时准备急停
4. **着装检查**：
   - 穿**紧身裤 / 打底裤**（宽松裤子遮挡动捕器导致追踪失效）
   - 上衣合身，避免超宽松袖子干扰手臂追踪
5. **绑脚踝动捕器**：分别绑到左右脚踝，**有指示灯的一面朝上**，裤腿向上卷起露出动捕器

#### 第二阶段：启动遥操系统

6. **确认 XRoboToolkit PC Service 运行**：
   ```bash
   # 若服务未启动，手动运行
   bash /opt/apps/roboticsservice/runService.sh
   ```
7. **戴上 PICO 头显**（额头式佩戴，确保 PICO 摄像头朝前以持续检测动捕器），打开 **XRoboToolKit App**
8. **确认 PICO 连接正常**：App 内 "Status:" 显示 **WORKING**，"Pico Motion Tracker" 选 **Full body**
9. **启动终端 1（C++ 真机推理）**，等待输出 **"Init done"**
10. **在终端 1 按 `]`** 启动 policy 控制权限
11. **启动终端 2（PICO 推流）**，确认终端输出体态数据帧率正常（50+ fps）

#### 第三阶段：校准与激活

12. **站好校准姿态**（在按 A+B+X+Y 前保持 1-2 秒）：
    - 站直，双脚并拢，目视正前方（不要低头看控制器）
    - 大臂自然垂直向下，紧贴躯干两侧
    - 小臂向前弯曲 90°（L 形肘），手掌朝内
13. **同时按 A+B+X+Y** → policy 初始化 + 全身校准（CALIB_FULL），机器人进入 **PLANNER** 模式开始自主平衡
14. **观察机器人**：确认机器人已稳定站立，调整自己的身体姿态与机器人当前姿态**尽量对齐**
15. **按 A+X** → 进入 **POSE** 模式，全身遥操激活，机器人开始实时跟随你的动作

#### 第四阶段：遥操中注意事项

16. **自然行走**：使用正常步伐和自然摆臂，不要刻意放慢或模仿机器人
17. **切换模式**：随时可按 **A+X** 从 POSE 切回 PLANNER（切换前先对齐姿态，避免机器人剧烈运动）
18. **长按 Menu 键**暂停姿态流（机器人保持当前动作），松开前先把身体调回机器人姿态
19. **重新校准**：若追踪质量下降（机器人动作漂移），按 **A+B+X+Y** 停止 → 重新站校准姿态 → 重新启动

#### 第五阶段：结束

20. **按 A+B+X+Y** 急停退出，机器人回到 OFF 状态停止运动
21. 等机器人**完全静止**后再摘下 PICO 头显和动捕器
22. 关闭终端 1 和终端 2

#### 紧急停止（任意时刻）

| 方式        | 操作                          |
| ----------- | ----------------------------- |
| PICO 控制器 | 同时按**A + B + X + Y** |
| 键盘        | 在终端 1 按**`O`**    |

---

## 10. Step 8：NX 板载真机 G1 遥操部署

> **前提：** 必须先完成 [Step 7 笔记本版](#9-step-7真机-g1-遥操部署笔记本版) 并确认控制链路完全正常，再迁移到 NX 板载。

NX 板载部署将所有软件跑在 G1 机载的 Jetson Orin NX 上，PICO 直接连接 NX，无需外接笔记本参与控制。

### 架构对比

```
笔记本版：
PICO → (WiFi) → 笔记本 → (Ethernet 192.168.123.x) → G1 电机

NX 板载版：
PICO → (WiFi) → G1 NX 板
                   ├── XRoboToolkit（arm64）
                   ├── pico_manager_thread_server.py
                   ├── g1_deploy_onnx_ref（ARM64 重新编译）
                   └── (内部总线) → G1 电机
```

| 对比项   | 笔记本版             | NX 板载版            |
| -------- | -------------------- | -------------------- |
| 调试难度 | 低（直接看终端输出） | 高（全程 SSH）       |
| GPU 算力 | 高（NVIDIA 独显）    | 低（Jetson Orin NX） |
| 电机延迟 | ~1ms（Ethernet）     | < 0.1ms（内部总线）  |
| 便携性   | 需带笔记本           | 纯机载，无需外接设备 |
| 推荐用于 | 开发调试             | 演示部署             |

### Step 8.1：将项目代码拷贝到 NX

在笔记本上执行：

```bash
scp -r ~/Noetix/Humanoid/WBM/GR00T-WholeBodyControl unitree@192.168.123.164:~/
```

### Step 8.2：安装 XRoboToolkit（arm64 版）

SSH 进入 NX 后执行：

```bash
ssh unitree@192.168.123.164

sudo dpkg -i ~/GR00T-WholeBodyControl/gear_sonic_deploy/thirdparty/roboticsservice_1.0.0.0_arm64.deb
```

> **注意：** NX 上的 XRoboToolkit 服务**不会自动启动**，每次需手动运行：
>
> ```bash
> bash /opt/apps/roboticsservice/runService.sh
> ```

### Step 8.3：在 NX 上安装 Python 遥操环境

```bash
cd ~/GR00T-WholeBodyControl
bash install_scripts/install_pico.sh
source .venv_teleop/bin/activate
```

### Step 8.4：在 NX 上编译 C++ 部署程序（ARM64）

NX 是 aarch64 架构，需在 NX 本机重新编译：

```bash
cd ~/GR00T-WholeBodyControl/gear_sonic_deploy
bash deploy.sh --input-type zmq_manager real
```

> 首次编译时间较长（15-30 分钟）。NX 使用 Jetson 版 TensorRT，需确认 JetPack 版本与 TensorRT 版本匹配。

### Step 8.5：配置 PICO 连接到 NX

在 PICO 的 XRoboToolKit App 中，将 PC Service 的 IP 从笔记本 IP **改为 NX 的 WiFi IP**：

```bash
# 在 NX 上查看 WiFi 接口 IP（非 192.168.123.x）
ip -4 addr show | grep -v "192.168.123\|127.0.0"
```

### Step 8.6：运行（全部 SSH 到 NX 上执行）

**终端 1（SSH）— 启动 XRoboToolkit 服务：**

```bash
bash /opt/apps/roboticsservice/runService.sh
```

**终端 2（SSH）— C++ 推理程序：**

```bash
cd gear_sonic_deploy
bash deploy.sh --input-type zmq_manager real
```

**终端 3（SSH）— PICO 遥操推流：**

```bash
source .venv_teleop/bin/activate
python gear_sonic/scripts/pico_manager_thread_server.py --manager
```

操作流程（校准姿态、按键、急停）与笔记本版完全一致。

---

## 11. PICO 按键完整速查

### 模式状态机

```
OFF ──(A+B+X+Y)──► PLANNER ──(A+X)──► POSE
                      │                  │
                      └─(L-Stick)──► VR_3PT
                                        │
                      任意模式 ──(A+B+X+Y)──► OFF（急停）
```

### 模式说明

| 模式                           | Encoder | 说明                                                   |
| ------------------------------ | ------- | ------------------------------------------------------ |
| **OFF**                  | --      | Policy 未运行，静止等待                                |
| **PLANNER**              | G1      | 运动规划器激活，上下半身由规划器驱动，摇杆控制行走方向 |
| **POSE**                 | SMPL    | 全身遥操，PICO 体态实时映射到机器人                    |
| **PLANNER_FROZEN_UPPER** | G1      | 规划器行走，上半身冻结在最后一次 POSE 快照             |
| **VR_3PT**               | TELEOP  | 规划器行走，上半身跟随 VR 3 点追踪（头 + 双手）        |

### 控制器按键

| 按键                       | 功能                              | 备注                                                                     |
| -------------------------- | --------------------------------- | ------------------------------------------------------------------------ |
| **A + B + X + Y**    | 启动/急停                         | 首次：启动 policy + 全身校准（CALIB_FULL）进入 PLANNER；再次：急停回 OFF |
| **A + X**            | 切换 POSE ↔ PLANNER              | 进入 POSE 前**必须先对齐身体姿态**                                 |
| **B + Y**            | 切换 POSE ↔ PLANNER_FROZEN_UPPER | 同上，切换前先对齐                                                       |
| **L-Stick Click**    | 进入/退出 VR_3PT                  | 每次进入时触发手腕重校准（CALIB），切入前先对齐手臂                      |
| **Trigger（左/右）** | 左/右手抓握                       |                                                                          |
| **Menu（长按）**     | 暂停姿态流                        | 松开前先把身体调回机器人姿态                                             |

### 摇杆控制（PLANNER / PLANNER_FROZEN_UPPER / VR_3PT 模式）

| 输入            | 功能                   |
| --------------- | ---------------------- |
| 左摇杆          | 移动方向（前/后/横向） |
| 右摇杆（水平）  | 偏航 / 转向（累积）    |
| **A + B** | 切换到下一个运动模式   |
| **X + Y** | 切换到上一个运动模式   |

### 运动模式列表

| ID    | 模式名                                |
| ----- | ------------------------------------- |
| 0     | Idle（默认）                          |
| 1     | 慢走 Slow Walk                        |
| 2     | 正常走 Walk                           |
| 3     | 跑步 Run                              |
| 4     | 蹲姿 Squat                            |
| 5     | 双膝跪 Kneel（two legs）              |
| 6     | 单膝跪 Kneel                          |
| 7     | 俯卧 Lying face-down                  |
| 8     | 爬行 Crawling                         |
| 9–16 | 格斗系列（Idle/Walk/Punch/Hook 变体） |
| 17    | 向前跳 Forward Jump                   |
| 18    | 隐蔽走 Stealth Walk                   |
| 19    | 受伤走 Injured Walk                   |

### 紧急停止

| 方式           | 操作                          |
| -------------- | ----------------------------- |
| PICO 控制器    | 同时按**A + B + X + Y** |
| 键盘（终端 2） | 按**`O`**                   |

---

## 12. 校准姿态与模式切换安全规范

### 校准姿态（CALIB_FULL，首次 A+B+X+Y 前必做）

首次按 A+B+X+Y 之前，**必须站好以下姿态并保持 1-2 秒**：

1. **站直**，双脚并拢，目视正前方（不要低头看控制器）
2. **大臂**自然垂直向下，紧贴躯干两侧
3. **小臂**向前弯曲 90°（手肘呈 L 形），手掌朝内

> 可用 `--vis_vr3pt` 参数启动终端 3，弹出的骨架窗口会显示参考姿态，对着它站好。

### 切换模式前的安全规则

> **危险场景举例：** 机器人在 PLANNER 模式下直立站着，你处于弯腰姿态，此时按 A+X 切换 POSE → 机器人会猛烈尝试跟随你的弯腰姿态，造成剧烈运动甚至摔倒。

**切换模式的正确流程：**

1. 观察机器人或可视化窗口，确认机器人当前姿态
2. 调整自己的身体姿态，与机器人**尽量一致**
3. 再按按键切换模式，过渡会平滑

**VR_3PT 模式坏校准的恢复：**

1. 按 **L-Stick Click** 退回 PLANNER（冻结上半身）
2. 重新对齐手臂与机器人当前手臂姿态
3. 按 **A + X** 切换到 POSE 模式重置

### 着装要求

| 部位 | 要求                                                                     |
| ---- | ------------------------------------------------------------------------ |
| 裤子 | **必须穿紧身裤/打底裤/运动紧身裤** — 宽松裤子遮挡动捕器，追踪失效 |
| 上衣 | 普通合身衣物即可，避免超宽松袖子干扰手臂追踪                             |

---

## 13. Unitree SDK2 与部署代码的桥接原理

### 通信协议层级

```
PICO → XRoboToolkit（Wi-Fi）
    → pico_manager_thread_server.py（ZMQ，端口 5556）
        → g1_deploy_onnx_ref（C++，zmq_manager input type）
            → Unitree SDK2（DDS / CycloneDDS）
                → G1 实体机器人（192.168.123.x）
                   或 MuJoCo 仿真（loopback）
```

### Unitree SDK2 在项目中的位置

```
gear_sonic_deploy/thirdparty/unitree_sdk2/   ← C++ SDK 源码
gear_sonic_deploy/thirdparty/roboticsservice_1.0.0.0_arm64.deb  ← Jetson 端 XRoboToolkit
install_scripts/install_pico.sh              ← 安装 unitree_sdk2_python（Python 绑定）
```

### C++ 部署端如何使用 SDK2

`g1_deploy_onnx_ref` 内部调用 Unitree SDK2 的 DDS 接口：

- **Sim 模式**（`deploy.sh sim`）：绑定 **loopback 接口（lo）**，通过 CycloneDDS 与 `run_sim_loop.py` 的 MuJoCo 仿真通信
- **Real 模式**（`deploy.sh real`）：绑定 **192.168.123.x 网络接口**，直接向 G1 机器人发送关节力矩指令

### pico_manager_thread_server.py 的桥接作用

该脚本是 PICO → G1 的中间层，主要工作：

1. 调用 XRoboToolkit Python SDK 读取 PICO 实时体态数据
2. 将 PICO 体态（头部位置 + 双手位置 + 全身关节角）转换为：
   - SMPL 姿态（24 关节 × 3D 位置）
   - G1 关节角度（29 个关节）
3. 打包成 ZMQ Protocol v3 消息，发布到 `localhost:5556`
4. 同时处理 PICO 控制器按键（A+X、A+B+X+Y 等），通过 ZMQ 向 C++ 端发送模式切换命令

### deploy.sh 参数解析

```bash
./deploy.sh --input-type zmq_manager sim
#           ↑ 使用 PICO ZMQ 管理器输入   ↑ 绑定 loopback（仿真）

./deploy.sh --input-type zmq_manager real
#                                    ↑ 自动检测 192.168.123.x（真机）

./deploy.sh --input-type zmq_manager --zmq-host 192.168.1.100 real
#                                    ↑ 遥操脚本在另一台机器上时指定 IP
```

---

## 14. 常见问题排查

**Q: XRoboToolKit App 连接 PC 显示 "FAILED" 或无反应？**

> A: 检查 PC Service 是否安装成功（`dpkg -l | grep xrobot`）。确认 PICO 和电脑在同一 Wi-Fi 子网。防火墙检查：`sudo ufw status`，若防火墙开启，允许 XRoboToolkit 端口（默认 7000）。

**Q: 终端 3 启动后无骨架窗口弹出？**

> A: PICO 未成功连接到 PC Service。重新检查 XRoboToolKit App 内的 IP 地址，点击 Reconnect。确认 "Status: WORKING"。

**Q: 机器人不跟踪脚部动作，只有上半身跟随？**

> A: 动捕器未正确配对或校准失败。重新执行 [Step 3](#5-step-3脚踝动捕器配置与校准) 的配对和校准流程。检查裤子是否过于宽松。

**Q: 按 A+B+X+Y 后机器人没反应？**

> A: 确认终端 2 已显示 "Init done" 且按 `]` 启动了 policy。检查终端 3 是否正在运行且 PICO 数据正在流入（观察终端 3 的输出）。

**Q: 切换到 POSE 模式后机器人剧烈运动？**

> A: 你的身体姿态与机器人当前姿态不一致。立即按 **A+B+X+Y** 急停，重新对齐姿态后再切换。

**Q: 遥操时机器人步伐不稳定、经常绊倒？**

> A: 主要原因：Wi-Fi 延迟过高（> 30ms）。使用私用路由器，避免公共 Wi-Fi。减少 PICO 和电脑之间的 Wi-Fi 跳数。另外，尽量走路自然，不要刻意放慢或模仿机器人动作。

**Q: 终端 2 输出 `WARNING: High ZMQ latency detected: XXms`？**

> A: 网络延迟过高，改善 Wi-Fi 环境或检查有没有其他设备占用带宽。

**Q: 脚踝动捕器配对后灯不亮 / 无响应？**

> A: 检查动捕器电量（充电后重试）。长按顶部按钮 6 秒观察灯光变化，红蓝交替闪烁才是配对模式。

**Q: 遥操脚本和 conda 环境冲突（Python 版本不对）？**

> A: 遥操脚本需在 `.venv_teleop` 中运行。若同时激活了 conda SONIC 环境，先 `deactivate`（退出 venv）再 `conda deactivate`，然后重新 `source .venv_teleop/bin/activate`。用 `which python` 确认指向 `.venv_teleop/bin/python`。
