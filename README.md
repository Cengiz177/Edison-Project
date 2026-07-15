## 项目结构

```
├── config.py          # 配置文件：环境、物理模型、训练参数
├── environment.py     # 环境模拟：风光储氢系统物理建模
├── agent.py          # 智能体：SAC算法实现和多智能体协调
├── train.py          # 训练脚本：强化学习训练流程
├── test.py           # 测试脚本：模型评估和结果分析
├── data/             # 数据目录
│   ├── 风速-温度-光强-全年.csv     # 训练数据（全年气象数据）
│   └── 冬典型月15日天气数据.csv   # 测试数据
├── models/           # 模型保存目录
├── requirements.txt  # 依赖包列表
└── README.md        # 项目说明文档
```

## 快速开始

### 1. 环境配置

```bash
# 安装依赖
pip install -r requirements.txt
```

### 2. 数据准备

确保数据文件位于正确位置：

- `data/风速-温度-光强-全年.csv` - 训练用全年气象数据
- `data/冬典型月15日天气数据.csv` - 测试用典型日数据

数据格式要求：

```csv
风速(m/s),温度(℃),光强(W/m²)
2.5,15.2,450.3
3.1,16.8,523.7
...
```

### 3. 模型训练

```bash
# 开始训练（默认1000回合）
python train.py

# 训练过程会自动保存4种最佳模型：
# - best_model_avg_efficiency    : 最佳平均效率模型
# - best_model_single_efficiency : 单回合最佳效率模型  
# - best_model_single_hydrogen   : 单回合最佳制氢量模型
# - final                        : 最终模型
```

### 4. 模型测试

```bash
# 测试指定目录下的所有模型
python test.py --model_path models/20241230-143022

# 自动运行100轮测试，选择最佳模型并生成详细报告
```