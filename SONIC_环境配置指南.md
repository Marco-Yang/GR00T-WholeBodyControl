# SONIC 环境配置保姆级文档

> 适用仓库：[GR00T-WholeBodyControl](https://github.com/NVlabs/GR00T-WholeBodyControl)
> conda 环境名称：`SONIC`

---

## 目录

1. [硬件 &amp; 系统前提条件](#1-硬件--系统前提条件)
2. [选择你要做什么（查表）](#2-选择你要做什么查表)
3. [通用准备：克隆仓库](#3-通用准备克隆仓库)
4. [方案 A：训练环境（Isaac Lab）](#4-方案-a训练环境isaac-lab)
5. [下载模型文件（ONNX + Checkpoint）](#5-下载模型文件onnx--checkpoint)
6. [方案 B：MuJoCo 仿真（sim2sim）](#6-方案-bmujoco-仿真sim2sim)
7. [方案 C：真机部署（C++ 推理）](#7-方案-c真机部署c-推理)
8. [方案 D：VR 遥操作环境](#8-方案-dvr-遥操作环境)
9. [方案 E：数据采集环境](#9-方案-e数据采集环境)
10. [验证环境](#10-验证环境)
11. [常见问题](#11-常见问题)

---

## 1. 硬件 & 系统前提条件

| 条件     | 要求                                                                      |
| -------- | ------------------------------------------------------------------------- |
| 操作系统 | Ubuntu 20.04 / 22.04 / 24.04                                              |
| Python   | **3.10**（Isaac Sim 4.5 严格要求 `==3.10.*`，3.11/3.12 均不兼容） |
| GPU      | NVIDIA GPU，CUDA 12.x                                                     |
| Git LFS  | 必须安装，否则大文件只会下载指针                                          |

**安装 Git LFS（必做）：**

```bash
sudo apt install git-lfs
git lfs install
```

**安装 Miniconda（如果还没有）：**

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc
```

下载链接：https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

---

## 2. 选择你要做什么（查表）

| 我想做…            | 需要的环境                                      | 对应章节                           |
| ------------------- | ----------------------------------------------- | ---------------------------------- |
| 训练 / 微调 SONIC   | Isaac Lab Python 环境 +`gear_sonic[training]` | [方案 A](#4-方案-a训练环境isaac-lab)  |
| MuJoCo sim2sim 测试 | `.venv_sim` + ONNX 模型 + TensorRT            | [方案 B](#6-方案-bmujoco-仿真sim2sim) |
| 真机 G1 部署        | ONNX 模型 + TensorRT + C++ 编译                 | [方案 C](#7-方案-c真机部署c-推理)     |
| PICO VR 遥操作      | `.venv_teleop`（自动创建）                    | [方案 D](#8-方案-dvr-遥操作环境)      |
| 采集演示数据        | `.venv_data_collection`（自动创建）           | [方案 E](#9-方案-e数据采集环境)       |

> **sim2sim / 真机部署都需要先完成 [第 5 节：下载模型文件](#5-下载模型文件onnx--checkpoint)，再安装 TensorRT 并编译 C++ 程序。**

---

## 3. 通用准备：克隆仓库

**以下步骤所有方案都需要执行一次：**

```bash
git clone https://github.com/NVlabs/GR00T-WholeBodyControl.git
cd GR00T-WholeBodyControl

# 拉取 LFS 大文件（网格、ONNX 模型等）
git lfs pull

# 验证环境基础状态
python check_environment.py
```

---

## 4. 方案 A：训练环境（Isaac Lab）

> 用途：从头训练或微调 SONIC policy（PPO + Isaac Lab 仿真）。

### 4.1 创建 conda 环境

```bash
conda create -n SONIC python=3.10 -y
conda activate SONIC
```

### 4.2 安装 Isaac Lab

SONIC 训练依赖以下精确版本组合：

| 组件                | 版本                                                     |
| ------------------- | -------------------------------------------------------- |
| **Isaac Sim** | **4.5.0.0**（pip 包四段式版本号）                  |
| **Isaac Lab** | **2.3.2**                                          |
| **Python**    | **3.10**（`Requires-Python ==3.10.*`，严格限定） |
| **CUDA**      | **12.x**                                           |

**官方安装文档：** https://isaac-sim.github.io/IsaacLab/main/source/setup/installation/index.html

#### 步骤 1：通过 pip 安装 Isaac Sim 4.5.0.0

```bash
conda activate SONIC

pip install isaacsim==4.5.0.0 \
    --extra-index-url https://pypi.nvidia.com

pip install \
    isaacsim-rl==4.5.0.0 \
    isaacsim-replicator==4.5.0.0 \
    isaacsim-extscache-physics==4.5.0.0 \
    isaacsim-extscache-kit==4.5.0.0 \
    isaacsim-extscache-kit-sdk==4.5.0.0 \
    --extra-index-url https://pypi.nvidia.com
```

#### 步骤 2：克隆并安装 Isaac Lab 2.3.2

```bash
git clone https://github.com/isaac-sim/IsaacLab.git
cd IsaacLab
git checkout v2.3.2
./isaaclab.sh --install
```

`./isaaclab.sh --install` 只安装 Isaac Sim 相关依赖，**不会** 自动将 `isaaclab` Python 包装入环境，需手动补装：

```bash
pip install -e source/isaaclab
pip install -e source/isaaclab_rl
```

Release 页面：https://github.com/isaac-sim/IsaacLab/releases/tag/v2.3.2

#### 步骤 3：验证安装

```bash
python -c "import isaaclab; print(isaaclab.__version__)"
# 应输出：0.54.2（git tag v2.3.2 对应的包版本）
```

### 4.3 安装 gear_sonic 训练依赖

```bash
cd ~/GR00T-WholeBodyControl   # 或你的仓库路径
pip install -e "gear_sonic/[training]"
```

> **如果 `flatdict==4.0.1` 构建失败**（`No module named 'pkg_resources'`），原因是 setuptools ≥ 80 破坏了旧式 setup.py 的隔离构建。修复方法：
>
> ```bash
> pip install "setuptools<80"
> pip install flatdict==4.0.1 --no-build-isolation
> pip install -e "gear_sonic/[training]"
> ```

### 4.4 安装额外缺失依赖

`gear_sonic` 有部分依赖未在 `pyproject.toml` 中声明，需手动补装：

```bash
pip install open3d vector-quantize-pytorch
```

### 4.5 安装 Isaac Sim asset 扩展包

Isaac Sim 的 URDF 导入器在独立包中，需额外安装：

```bash
pip install isaacsim-asset==4.5.0.0 --extra-index-url https://pypi.nvidia.com
```

### 4.6 修复 Isaac Lab headless kit 文件

Isaac Lab 2.3.2 的 headless kit 文件缺少 `isaacsim.asset.importer.urdf` 扩展声明，导致训练启动时找不到 URDF 导入器。

编辑 `<IsaacLab目录>/apps/isaacsim_4_5/isaaclab.python.headless.kit`，在 Isaac Sim Extensions 区块末尾添加一行：

```toml
########################
# Isaac Sim Extensions #
########################
[dependencies]
"isaacsim.simulation_app" = {}
"isaacsim.core.api" = {}
"isaacsim.core.cloner" = {}
"isaacsim.core.utils" = {}
"isaacsim.core.version" = {}
"isaacsim.asset.importer.urdf" = {}   # ← 添加这一行
```

### 4.7 修复 Isaac Lab urdf_converter API 兼容性

Isaac Lab 2.3.2 调用了 `isaacsim.asset.importer.urdf` 中一个新版本才有的方法
`set_merge_fixed_ignore_inertia`，而 pip 安装的扩展版本（2.3.10）尚不包含此方法。

编辑 `<IsaacLab目录>/source/isaaclab/isaaclab/sim/converters/urdf_converter.py`，
将第 142–143 行改为：

```python
import_config.set_merge_fixed_joints(self.cfg.merge_fixed_joints)
if hasattr(import_config, "set_merge_fixed_ignore_inertia"):
    import_config.set_merge_fixed_ignore_inertia(self.cfg.merge_fixed_joints)
```

### 4.8 冒烟测试（验证训练环境可用）

```bash
python check_environment.py --training

# 冒烟测试（5 步，有 GUI）
python gear_sonic/train_agent_trl.py \
    +exp=manager/universal_token/all_modes/sonic_release \
    num_envs=16 headless=False \
    ++algo.config.num_learning_iterations=5

# 无显示器 / 服务器模式
python gear_sonic/train_agent_trl.py \
    +exp=manager/universal_token/all_modes/sonic_release \
    num_envs=16 headless=True \
    ++algo.config.num_learning_iterations=5
```

约 1 分钟初始化后控制台打印训练指标即为成功。

### 4.9 完整训练

```bash
accelerate launch --num_processes=8 gear_sonic/train_agent_trl.py \
    +exp=manager/universal_token/all_modes/sonic_release \
    +checkpoint=sonic_release/last.pt \
    num_envs=4096 headless=True \
    ++manager_env.commands.motion.motion_lib_cfg.motion_file=data/motion_lib_bones_seed/robot_filtered \
    ++manager_env.commands.motion.motion_lib_cfg.smpl_motion_file=data/smpl_filtered
```

---

## 5. 下载模型文件（ONNX + Checkpoint）

> **sim2sim 和真机部署都需要先完成本节。** 模型托管在 HuggingFace（公开，无需 token）：
> https://huggingface.co/nvidia/GEAR-SONIC

### 5.1 注意：运行前先确认 Python 环境

项目有多个虚拟环境（`.venv_sim`、`.venv_teleop` 等），如果这些 venv 处于激活状态，
`python` 命令会指向 venv 的 Python，而不是 `SONIC` conda 环境的 Python，
导致 `huggingface_hub` 找不到。

**运行下载脚本之前，先退出所有 venv：**

```bash
deactivate          # 退出当前激活的 venv（如 .venv_sim）
conda activate SONIC
```

或直接用 SONIC 环境的完整路径：

```bash
/home/adam/anaconda3/envs/SONIC/bin/python download_from_hf.py
```

**如何判断是否有 venv 冲突：** 提示符同时出现 `(SONIC)` 和 `(gear_sonic_sim)` 等括号，
说明 conda 和 venv 同时激活，venv 会覆盖 conda。

### 5.2 下载部署用 ONNX 模型（sim2sim / 真机必须）

```bash
conda activate SONIC
cd ~/GR00T-WholeBodyControl

python download_from_hf.py
```

下载内容及目标位置：

```
gear_sonic_deploy/
├── policy/release/
│   ├── model_encoder.onnx        ← encoder 网络
│   ├── model_decoder.onnx        ← decoder 网络
│   └── observation_config.yaml
└── planner/target_vel/V2/
    └── planner_sonic.onnx        ← 运动规划器
```

如果不需要运动规划器（纯 policy 测试）：

```bash
python download_from_hf.py --no-planner
```

### 5.3 下载训练用 Checkpoint（训练 / 微调必须）

```bash
# 下载 checkpoint + SMPL 数据（~30 GB，可能很慢）
python download_from_hf.py --training

# 只下载 checkpoint，跳过 30 GB SMPL 数据
python download_from_hf.py --training --no-smpl

# 只下载小样本数据用于快速测试（~4 MB）
python download_from_hf.py --sample
```

下载后文件布局：

```
sonic_release/
├── last.pt          ← 训练 checkpoint
└── config.yaml
data/smpl_filtered/  ← SMPL 数据（--training 时下载）
```

### 5.4 下载训练数据 Bones-SEED（可选，全量训练才需要）

数据集主页：https://huggingface.co/datasets/bones-studio/seed

```bash
# Step 1：将 G1 重定向 CSV 转换格式
python gear_sonic/data_process/convert_soma_csv_to_motion_lib.py \
    --input /path/to/bones_seed/g1/csv/ \
    --output data/motion_lib_bones_seed/robot \
    --fps 30 --fps_source 120 --individual --num_workers 16

# Step 2：过滤 G1 无法执行的动作（约过滤 8.7%）
python gear_sonic/data_process/filter_and_copy_bones_data.py \
    --source data/motion_lib_bones_seed/robot \
    --dest data/motion_lib_bones_seed/robot_filtered --workers 16
```

---

## 6. 方案 B：MuJoCo 仿真（sim2sim）

> 用途：在 MuJoCo 仿真器里测试 SONIC policy（policy 运行在 C++ 推理程序中，通过 DDS 通信）。
> **前置条件：先完成 [第 5 节：下载 ONNX 模型](#5-下载模型文件onnx--checkpoint)。**

### 6.1 安装 MuJoCo 仿真环境

项目脚本会用 `uv` 创建 `.venv_sim` 虚拟环境：

```bash
bash install_scripts/install_mujoco_sim.sh
```

脚本自动完成：

- 安装 `uv`（如未安装）
- 创建 `.venv_sim` 虚拟环境
- 安装 `gear_sonic[sim]`（MuJoCo、Pinocchio、PyZMQ 等）
- 安装 `unitree_sdk2_python`

### 6.2 安装 TensorRT 并编译 C++ 部署程序

**sim2sim 需要 C++ deploy 二进制与 MuJoCo sim 进程通过 DDS 通信，必须先安装 TensorRT 才能编译。**

x86_64 桌面要求 **TensorRT 10.13**（版本必须精确匹配，版本错误会导致推理结果静默出错）。

**下载 TensorRT TAR 包**（需登录 NVIDIA Developer 账户）：

```
https://developer.nvidia.com/tensorrt/download/10x
```

选：TensorRT 10.13.x for Linux x86_64 and CUDA 12.x，**TAR 包**（不是 DEB）。

```bash
# 解压并移动到 ~/TensorRT
tar -xzf TensorRT-10.13.*.Linux.x86_64-gnu.cuda-12.*.tar.gz -C $HOME
mv $HOME/TensorRT-10.13.* $HOME/TensorRT

# 写入 ~/.bashrc（永久生效）
echo 'export TensorRT_ROOT=$HOME/TensorRT' >> ~/.bashrc
export TensorRT_ROOT=$HOME/TensorRT

# 验证
ls $TensorRT_ROOT/lib/libnvinfer.so*
```

**安装系统依赖并编译：**

```bash
cd gear_sonic_deploy
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh

source scripts/setup_env.sh
just build
```

### 6.3 运行 sim2sim

需要**两个终端同时运行**：

**Terminal 1 — MuJoCo 仿真器：**

```bash
cd ~/GR00T-WholeBodyControl
source .venv_sim/bin/activate
python gear_sonic/scripts/run_sim_loop.py
```

**Terminal 2 — C++ 部署程序（连接 sim）：**

```bash
cd ~/GR00T-WholeBodyControl/gear_sonic_deploy
bash deploy.sh sim
```

`deploy.sh sim` 默认使用：

- `policy/release/model_decoder.onnx` / `model_encoder.onnx`
- `planner/target_vel/V2/planner_sonic.onnx`
- `reference/example/` 参考运动数据

**操作步骤：**

1. 先启动终端 1（MuJoCo 窗口出现后），再启动终端 2
2. MuJoCo 窗口中按 `9` 开启弹性辅助力，机器人站稳
3. 终端 2 出现以下提示后说明 DDS 已就绪：
   ```
   g1_deploy_: selected interface "lo" is not multicast-capable: disabling multicast
   ```
4. 终端 2 中按 `]` 启动 policy
5. 按 `Enter` 开启 Planner，机器人可响应 WASD 行走指令

---

**MuJoCo 窗口按键（终端 1 / run_sim_loop.py）：**

| 按键 | 功能 |
|---|---|
| `9` | 开/关弹性辅助力（Elastic Band，帮助机器人保持直立） |
| `Backspace` | 重置仿真状态 |
| `V` | 切换视角（第一视角 / 自由视角） |
| `↑ ↓ ← →` | 对机器人施加外力扰动 |

---

**deploy 终端按键（终端 2 / deploy.sh sim）：**

> 按键分两种模式，用 `Enter` 切换。

**全局按键（两种模式均有效）：**

| 按键 | 功能 |
|---|---|
| `]` | 启动 policy（开始控制） |
| `O` | 停止控制并退出 |
| `Enter` | 开/关 Planner（行走/转向必须开启） |
| `I` | 重置朝向（base quaternion + delta heading） |
| `T` | 播放当前参考动作到末帧 |
| `Z` | 切换 encoder 模式（0 / 1） |
| `` ` `` / `~` | Planner 紧急停止（仅 Planner 开启时） |

**Planner 关闭模式（默认，参考动作浏览）：**

| 按键 | 功能 |
|---|---|
| `N` | 下一个动作序列 |
| `P` | 上一个动作序列 |
| `R` | 从头重播当前动作 |
| `Q` | 朝向左转 −0.1 |
| `E` | 朝向右转 +0.1 |
| `H` | 打印各电机温度 |

**Planner 开启模式（按 `Enter` 后，运动控制）：**

| 按键 | 功能 |
|---|---|
| `W` / `S` | 向前 / 向后移动 |
| `A` / `D` | 斜向左 / 斜向右移动 |
| `,` / `.` | 横向左平移 / 横向右平移 |
| `J` / `L` | 朝向左转 / 右转 |
| `Q` / `E` | 朝向微调右转 / 左转（±0.1） |
| `N` / `P` | 切换下一组 / 上一组动作集（站立/蹲/格斗…） |
| `1` ～ `8` | 直接选择当前动作集内的运动模式 |
| `-` / `=` | 目标高度 −0.1 / +0.1 |
| `9` / `0` | 移动速度 −0.1 / +0.1 |
| `R` | Planner 紧急停止（同 `` ` ``） |
| `F` | 打印各电机温度 |

---

## 7. 方案 C：真机部署（C++ 推理）

> 用途：在真实 Unitree G1 机器人上运行 SONIC policy。
> **前置条件：先完成 [第 5 节：下载 ONNX 模型](#5-下载模型文件onnx--checkpoint)。**

### 7.1 系统要求

| 平台                      | TensorRT 版本                                              |
| ------------------------- | ---------------------------------------------------------- |
| x86_64 桌面（遥控端）     | **10.13**（TAR 包手动安装，必须精确匹配）            |
| Jetson Orin NX（G1 机载） | **10.3.0.30**（JetPack 6 / L4T R36.4 apt 包）         |

> **警告：** TensorRT 版本必须与编译时使用的版本兼容，版本不对会导致推理结果静默错误，机器人可能产生危险动作。

### 7.2 安装 TensorRT

#### 7.2.1 x86_64 桌面

与 [6.2 节](#62-安装-tensorrt-并编译-c-部署程序) 相同，下载 TAR 包后解压并设置 `TensorRT_ROOT`。

#### 7.2.2 Jetson Orin NX（G1 机载，推荐方式）

Jetson 上 TensorRT 通过 JetPack apt 仓库安装，**不需要**下载 TAR 包：

```bash
sudo apt-get update
sudo apt-get install -y tensorrt
```

安装完后验证：

```bash
dpkg -l | grep libnvinfer
# 应看到 libnvinfer10 等包，以及对应版本号
```

Jetson 的 TensorRT 库安装在系统路径（`/usr/lib/aarch64-linux-gnu/`），**无需**手动设置 `TensorRT_ROOT`，`setup_env.sh` 会自动检测。

### 7.3 下载 ONNX 模型

部署需要三个 ONNX 文件，位于 `gear_sonic_deploy/` 下。如果已完成 [第 5 节](#5-下载模型文件onnx--checkpoint) 可跳过此步。

**激活 conda 环境后下载：**

```bash
conda activate SONIC
cd ~/Humanoid/GR00T-WholeBodyControl

# 确认 huggingface_hub 已安装
pip install huggingface_hub -q

# 下载部署用 ONNX 模型
unset HF_ENDPOINT
python download_from_hf.py
```

> **网络问题（国内）：** 如果连接 HuggingFace 超时，先设置镜像再运行：
> ```bash
> export HF_ENDPOINT=https://hf-mirror.com
> python download_from_hf.py
> ```

下载完成后验证文件存在：

```bash
ls gear_sonic_deploy/policy/release/
# 应包含：model_encoder.onnx  model_decoder.onnx  observation_config.yaml

ls gear_sonic_deploy/planner/target_vel/V2/
# 应包含：planner_sonic.onnx
```

### 7.4 安装系统依赖并构建

```bash
cd ~/Humanoid/GR00T-WholeBodyControl/gear_sonic_deploy

# 安装编译依赖（cmake, clang, just 等）
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh

# 配置运行时环境变量并写入 ~/.bashrc（只需做一次）
source scripts/setup_env.sh
echo "source $(pwd)/scripts/setup_env.sh" >> ~/.bashrc

# 编译 C++ 部署程序
just build
```

编译成功后验证：

```bash
just --list
# 应看到 g1_deploy_onnx_ref 等 target
```

### 7.5 部署到真机

确保机器人网线已连接（G1 机器人默认网段为 `192.168.123.x`）：

```bash
cd ~/Humanoid/GR00T-WholeBodyControl/gear_sonic_deploy

# 自动检测 192.168.123.x 机器人网络接口并启动
bash deploy.sh real

# 或指定网卡名
bash deploy.sh enP8p1s0
```

脚本会依次完成：文件检查 → 环境配置 → 重新编译 → 确认提示 → 启动推理程序。

**启动后按键操作：**

| 按键 | 功能 |
|------|------|
| `]` | 启动 policy（开始控制） |
| `Enter` | 开/关 Planner（行走必须开启） |
| `W` / `S` | 向前 / 向后 |
| `A` / `D` | 斜向左 / 斜向右 |
| `,` / `.` | 横向左平移 / 右平移 |
| `J` / `L` | 朝向左转 / 右转 |
| `O` | 停止控制并退出 |

完整按键表见 [6.3 节](#63-运行-sim2sim)。

### 7.6 Docker 方式（含 ROS2 开发环境）

```bash
sudo usermod -aG docker $USER
newgrp docker

export TensorRT_ROOT=$HOME/TensorRT

cd gear_sonic_deploy
./docker/run-ros2-dev.sh

# 容器内
source scripts/setup_env.sh
just build
```

---

## 8. 方案 D：VR 遥操作环境

> 用途：通过 PICO VR 头显进行全身遥操作，用于数据采集和交互控制。

### 8.1 一键安装

```bash
bash install_scripts/install_pico.sh
```

脚本自动完成：

- 安装 `uv` 和 Python 3.10
- 创建 `.venv_teleop` 虚拟环境
- 安装 `gear_sonic[teleop]`（PyZMQ、msgpack、Pinocchio、PyVista）
- 安装 `XRoboToolkit SDK`
- 安装 `gear_sonic[sim]` 和 `unitree_sdk2_python`（x86 时）

### 8.2 激活环境

```bash
source .venv_teleop/bin/activate
# 提示符中应显示 (gear_sonic_teleop)
```

VR 遥操作详细设置参考官方文档：https://nvlabs.github.io/GR00T-WholeBodyControl/getting_started/vr_teleop_setup.html

---

## 9. 方案 E：数据采集环境

> 用途：将遥操作演示录制为 LeRobot 格式数据集，用于后续 VLA 训练。

### 9.1 安装系统依赖

```bash
sudo apt-get install -y espeak   # 语音反馈（可选）
```

### 9.2 一键安装

```bash
bash install_scripts/install_data_collection.sh
```

脚本自动完成：

- 安装 `uv` 和 Python 3.10
- 创建 `.venv_data_collection` 虚拟环境
- 安装 `gear_sonic[data_collection]`（LeRobot、PyAV、OpenCV、PyZMQ 等）

### 9.3 激活并运行

```bash
source .venv_data_collection/bin/activate
python gear_sonic/scripts/run_data_exporter.py
```

---

## 10. 验证环境

```bash
# 基础验证（所有方案都可用）
python check_environment.py

# 训练环境专项验证
python check_environment.py --training
```

---

## 11. 常见问题

**Q: 运行 `python download_from_hf.py` 提示 `huggingface_hub is not installed`，但 pip show 显示已安装？**

> A: 提示符同时出现 `(SONIC)` 和 `(gear_sonic_sim)` 说明 `.venv_sim` 覆盖了 conda 的 Python。
> 先 `deactivate` 退出 venv，再运行；或用完整路径 `/home/adam/anaconda3/envs/SONIC/bin/python download_from_hf.py`。

**Q: `git lfs pull` 下载了但文件还是很小（只有几百字节）？**

> A: Git LFS 没有正确安装。先 `sudo apt install git-lfs && git lfs install`，再重新 `git lfs pull`。

**Q: `uv` 命令找不到？**

> A: 安装脚本会自动安装 uv，但需要 `source ~/.bashrc` 或 `export PATH="$HOME/.local/bin:$PATH"` 使其生效。

**Q: `isaacsim==4.5.0` 找不到版本？**

> A: pip 包使用四段式版本号，正确写法是 `isaacsim==4.5.0.0`（四段）。

**Q: Isaac Lab 安装后 `import isaaclab` 报 `ModuleNotFoundError`？**

> A: `./isaaclab.sh --install` 不会自动装 isaaclab Python 包，需手动 `pip install -e source/isaaclab`。

**Q: `flatdict` 构建失败：`No module named 'pkg_resources'`？**

> A: setuptools ≥ 80 破坏旧式 setup.py。执行：
>
> ```bash
> pip install "setuptools<80"
> pip install flatdict==4.0.1 --no-build-isolation
> ```

**Q: `mujoco` 安装失败，提示找不到 aarch64 wheel？**

> A: MuJoCo 在 Jetson Orin 上跳过安装是正常行为，仿真环境只需在 x86 桌面使用。

**Q: TensorRT 推理出来机器人动作不对？**

> A: 必须严格使用文档指定版本（x86: 10.13，Jetson Orin NX: 10.7），版本不匹配会产生静默错误。

**Q: `deploy.sh sim` 报文件缺失（`❌ Missing file: policy/release/model_decoder.onnx`）？**

> A: ONNX 文件未下载。先在 SONIC conda 环境执行 `python download_from_hf.py`（注意退出 venv 后再运行）。

**Q: Isaac Lab 安装报错 CUDA 版本不匹配？**

> A: 训练需要 CUDA 12.x，使用 `nvidia-smi` 检查当前驱动。

**Q: 训练时报 `SMPLSim` 安装失败？**

> A: SMPLSim 通过 git 安装，需要访问 GitHub，国内建议配置代理后再运行。
