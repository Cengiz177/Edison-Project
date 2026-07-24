import numpy as np

try:
    import torch
except ModuleNotFoundError:
    torch = None

class Config:
    # 环境参数
    ENV_PARAMS = {
        'train_data_path': 'data/风速-温度-光强-全年.csv',
        'test_data_path': 'data\冬典型月15日天气数据.csv',
        'time_steps': 24,  # 每个episode的时间步数
        'normalize_input': True,
    }
    
    # 物理模型参数
    PHYSICAL_PARAMS = {
        # 风机参数
        'wind_turbine': {
            'rated_power': 7000,  # 额定功率(kW)
            'cut_in_speed': 1,    # 切入风速(m/s)
            'cut_out_speed': 25,  # 切出风速(m/s)
            'rated_speed': 12,    # 额定风速(m/s)
            'blade_radius': 68,   # 叶片半径(m)
            'air_density': 1.205, # 空气密度(kg/m^3)
        },
        
        # 光伏参数
        'pv': {
            'rated_power': 5000,              # 调度环境最大可用功率(kW)
            'reference_irradiance': 1000,     # 参考辐照度(W/m^2)
            'reference_temperature': 25,      # 参考组件温度(℃)
            'temperature_coefficient': -0.0038,  # 最大功率温度系数(1/℃)
        },
        
        # 储能参数
        'battery': {
            # 16 柜 CATL EnerOne 1P：16 * 372.7 kWh = 5963.2 kWh。
            'model': 'CATL EnerOne 1P (16 cabinets)',
            'capacity': 5963.2,              # 额定能量(kWh)
            'rated_voltage': 1331.2,         # 单柜额定电压(V)，不参与SOC计算
            'max_charge_power': 5963.2,      # 最大充电功率(kW)
            'max_discharge_power': 5963.2,   # 最大放电功率(kW)
            # 当前为系统级建模假设，后续可根据PCS/实测数据调整。
            'charge_efficiency': 0.95,
            'discharge_efficiency': 0.95,
            'min_soc': 0.0,                  # 物理最小SOC
            'max_soc': 1.0,                  # 物理最大SOC
            'recommended_min_soc': 0.2,      # 推荐运行区间下限
            'recommended_max_soc': 0.8,      # 推荐运行区间上限
            'initial_soc': 0.5,              # 初始SOC
        },
        
        # 电解槽参数
        'electrolyzer': {
            'count': 4,           # 电解槽数量
            'max_power': 2500,    # 单台最大功率(kW)
            'min_power': 250,     # 最小运行功率(kW)
            'recommended_power': 150,  # 推荐功率(kW)
            'standby_power': 50,  # 待机功率(kW)
        },
        
        # 制氢效率参数
        'hydrogen_production': {
            'linear_coef': 205.31,        # 线性电解槽系数
            'nonlinear_coef_a': -11.24,   # 非线性电解槽系数a
            'nonlinear_coef_b': 232.7,    # 非线性电解槽系数b
            'fixed_consumption': 17.85,   # 固定消耗
            'standby_consumption': 8.89,  # 待机消耗
        }
    }
    
    # CTDE-SAC参数
    AGENT_PARAMS = {
        # 通用参数
        'common': {
            'hidden_dim': 256,         # 隐藏层维度
            'lr_actor': 3e-4,          # 演员学习率
            'lr_critic': 3e-4,         # 评论家学习率
            'gamma': 0.99,             # 折扣因子
            'tau': 0.01,              # 目标网络软更新参数
            'alpha': 0.2,              # 熵正则化系数
            'auto_alpha_tuning': True, # 自动调整alpha
            'buffer_size': 1000000,    # 经验回放缓冲区大小
            'batch_size': 512,         # 批次大小
            'hidden_layers': 5,
            # A string also works with PyTorch APIs and keeps the physical
            # environment importable when training dependencies are absent.
            'device': 'cuda' if torch is not None and torch.cuda.is_available() else 'cpu'
        },
        
        # 储能智能体
        'battery': {
            'state_dim': 14,           # 状态维度
            'action_dim': 1,           # 动作维度
        },
        
        # 电解槽智能体
        'electrolyzer': {
            'state_dim': 14,           # 状态维度
            'action_dim': 1,           # 动作维度
        }
    }
    
    # 训练参数
    TRAIN_PARAMS = {
        'episodes': 1000,             # 训练回合数
        'save_interval': 50,          # 保存间隔
        'eval_interval': 50,           # 评估间隔
        'update_interval': 1,          # 更新间隔
        'reward_weights': {
            'hydrogen': 1000.0,           # 制氢量权重
            'consumption': 1,        # 消纳率权重
            'switching': 2,          # 启停惩罚权重
        }
    }
