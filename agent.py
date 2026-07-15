import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from config import Config
import os

class ReplayBuffer:
    """经验回放缓冲区，用于存储和采样训练数据"""
    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = []
        self.position = 0
    
    def add(self, state, action, reward, next_state, done):
        """添加经验到缓冲区"""
        if len(self.buffer) < self.capacity:
            self.buffer.append(None)
        self.buffer[self.position] = (state, action, reward, next_state, done)
        self.position = (self.position + 1) % self.capacity
    
    def sample(self, batch_size):
        """从缓冲区随机采样批次数据"""
        batch_indices = np.random.choice(len(self.buffer), batch_size, replace=False)
        
        states = [self.buffer[i][0] for i in batch_indices]
        actions = [self.buffer[i][1] for i in batch_indices]
        rewards = [self.buffer[i][2] for i in batch_indices]
        next_states = [self.buffer[i][3] for i in batch_indices]
        dones = [self.buffer[i][4] for i in batch_indices]
        
        return states, actions, rewards, next_states, dones
    
    def __len__(self):
        return len(self.buffer)

class GaussianPolicy(nn.Module):
    """高斯策略网络，输出动作的均值和标准差"""
    def __init__(self, state_dim, action_dim, hidden_dim, action_space=None, hidden_layers=5):
        super(GaussianPolicy, self).__init__()
        
        layers = []
        layers.append(nn.Linear(state_dim, hidden_dim))
        layers.append(nn.ReLU())
        
        for i in range(4):
            layers.append(nn.Linear(hidden_dim, hidden_dim))
            layers.append(nn.ReLU())
            
        self.net = nn.Sequential(*layers)
        
        self.mean = nn.Linear(hidden_dim, action_dim)
        self.log_std = nn.Linear(hidden_dim, action_dim)
        self.action_space = action_space
        
        # 针对电池智能体的特殊初始化
        if 'battery' in str(self):
            nn.init.uniform_(self.mean.weight, -0.1, 0.1)
            nn.init.constant_(self.mean.bias, 0)
        else:
            nn.init.constant_(self.mean.bias, 0.3)
            nn.init.constant_(self.mean.weight, 0.01)
    
    def forward(self, state):
        """前向传播，计算动作均值和对数标准差"""
        x = self.net(state)
        mean = self.mean(x)
        
        # 电池智能体的特殊处理
        if 'battery' in str(self):
            mean = torch.tanh(mean) * 1.5
            mean = torch.clamp(mean, -1, 1)
        log_std = self.log_std(x)
        
        # 调整不同智能体的标准差范围
        if 'battery' in str(self):
            log_std = torch.clamp(log_std, -20, 0)
        else:
            log_std = torch.clamp(log_std, -20, 2)
            
        return mean, log_std
    
    def sample(self, state):
        """采样动作并计算对数概率"""
        mean, log_std = self.forward(state)
        std = log_std.exp()
        normal = torch.distributions.Normal(mean, std)

        if 'battery' in str(self):
            # 根据SOC状态调整电池行为
            soc_indicators = (state > 0.2) & (state < 0.8)
            
            if torch.any(soc_indicators):
                possible_soc = state[soc_indicators].max()
                
                min_soc = 0.2
                discharge_bias = min(0.8, (possible_soc - min_soc) * 3.0)
                
                temperature = min(1.2, 0.8 + (possible_soc - min_soc))
                mean = mean - discharge_bias
            else:
                temperature = 0.8
                mean = mean - 0.2
        else:
            temperature = 1.2
        
        x_t = normal.rsample() * temperature
        y_t = torch.tanh(x_t)
        
        # 计算对数概率
        log_prob = normal.log_prob(x_t)
        log_prob -= torch.log(1 - y_t.pow(2) + 1e-6)
        log_prob = log_prob.sum(1, keepdim=True)

        # 缩放动作到动作空间范围
        if self.action_space is not None:
            action = y_t * (self.action_space.high - self.action_space.low) / 2 + (self.action_space.high + self.action_space.low) / 2
        else:
            action = y_t

        return action, log_prob, torch.tanh(mean)



class QNetwork(nn.Module):
    """双Q网络，用于值函数估计"""
    def __init__(self, num_inputs, num_actions, hidden_dim, hidden_layers=4):
        super(QNetwork, self).__init__()
        
        # Q1网络
        self.q1 = nn.Sequential(
            nn.Linear(num_inputs + num_actions, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )
        
        # Q2网络，结构与Q1相同
        self.q2 = nn.Sequential(
            nn.Linear(num_inputs + num_actions, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )
    
    def forward(self, state, action):
        """前向传播，返回两个Q值"""
        x = torch.cat([state, action], dim=1)
        return self.q1(x), self.q2(x)

class SACAgent:
    """SAC（Soft Actor-Critic）智能体"""
    def __init__(self, state_dim, action_dim, agent_name="agent", action_space=None, hidden_dim=512,
                hidden_layers=2, lr_actor=5e-4, lr_critic=5e-4, gamma=0.995, tau=0.01, alpha=0.3,
                auto_alpha_tuning=True, device=torch.device("cpu")):
        self.gamma = gamma
        self.tau = tau
        self.alpha = alpha
        self.auto_alpha_tuning = auto_alpha_tuning
        self.device = device
        self.agent_name = agent_name
        self.action_dim = action_dim
        
        # 初始化策略网络
        self.policy = GaussianPolicy(state_dim, action_dim, hidden_dim, action_space, hidden_layers).to(device)
        self.policy_optimizer = optim.Adam(self.policy.parameters(), lr=lr_actor)
        
        # 初始化Q网络
        self.q_network = QNetwork(state_dim, action_dim, hidden_dim, hidden_layers).to(device)
        self.q_optimizer = optim.Adam(self.q_network.parameters(), lr=lr_critic)
        
        # 初始化目标Q网络
        self.target_q_network = QNetwork(state_dim, action_dim, hidden_dim, hidden_layers).to(device)
        for target_param, param in zip(self.target_q_network.parameters(), self.q_network.parameters()):
            target_param.data.copy_(param.data)
        
        # 自动调节熵系数
        if auto_alpha_tuning:
            self.target_entropy = -action_dim
            self.log_alpha = torch.zeros(1, requires_grad=True, device=device)
            self.alpha_optimizer = optim.Adam([self.log_alpha], lr=lr_actor)

        # 智能体特殊配置
        if 'electrolyzer' in agent_name:
            self.alpha = 1.0
        else:
            self.alpha = alpha
            
        self.auto_alpha_tuning = auto_alpha_tuning
    
    def select_action(self, state, evaluate=False):
        """选择动作"""
        state = torch.FloatTensor(state).unsqueeze(0).to(self.device)

        if evaluate:
            _, _, action = self.policy.sample(state)
            noise_scale = 0.1
            noise = torch.randn_like(action) * noise_scale
            action = torch.clamp(action + noise, -1, 1)
        else:
            action, _, _ = self.policy.sample(state)

            # 电池智能体的额外噪声
            if self.agent_name == 'battery':
                direction = np.sign(np.random.randn())
                noise = direction * np.random.uniform(0.1, 0.3)
                action += noise
                action = torch.clamp(action, -1, 1)

        return action.detach().cpu().numpy()[0]

    
    def update_parameters(self, memory, batch_size, updates):
        """更新网络参数"""
        states, actions, rewards, next_states, dones = memory.sample(batch_size)
        
        rewards = torch.FloatTensor(np.array(rewards)).unsqueeze(1).to(self.device)
        dones = torch.FloatTensor(np.array(dones)).unsqueeze(1).to(self.device)
        
        # 处理状态和动作数据
        state_tensors = []
        next_state_tensors = []
        agent_actions = []
        
        for i in range(batch_size):
            state_val = states[i][self.agent_name] if isinstance(states[i], dict) else states[i]
            next_state_val = next_states[i][self.agent_name] if isinstance(next_states[i], dict) else next_states[i]
            
            state_tensors.append(torch.FloatTensor(state_val))
            next_state_tensors.append(torch.FloatTensor(next_state_val))
            
            # 确定动作索引
            if self.agent_name == 'battery':
                agent_action_idx = 0
            else:
                idx = int(self.agent_name.split('_')[1])
                agent_action_idx = idx + 1
            
            if agent_action_idx < len(actions[i]):
                agent_action = actions[i][agent_action_idx]
                if isinstance(agent_action, np.ndarray):
                    agent_actions.append(torch.FloatTensor(agent_action.reshape(1)))
                else:
                    agent_actions.append(torch.FloatTensor(np.array([agent_action], dtype=np.float32)))
            else:
                agent_actions.append(torch.zeros(1))
        
        states_batch = torch.stack(state_tensors).to(self.device)
        next_states_batch = torch.stack(next_state_tensors).to(self.device)
        actions_batch = torch.stack(agent_actions).to(self.device)
        
        # 调整动作批次维度
        if actions_batch.dim() == 2 and actions_batch.size(1) == 1 and self.action_dim == 1:
            pass
        else:
            actions_batch = actions_batch.view(batch_size, -1)
            if actions_batch.size(1) != self.action_dim:
                actions_batch = actions_batch.repeat(1, self.action_dim)
        
        # 计算目标Q值
        with torch.no_grad():
            next_actions, next_log_probs, _ = self.policy.sample(next_states_batch)
            next_q1, next_q2 = self.target_q_network(next_states_batch, next_actions)
            next_q = torch.min(next_q1, next_q2) - self.alpha * next_log_probs
            target_q = rewards + (1 - dones) * self.gamma * next_q
        
        # 更新Q网络
        current_q1, current_q2 = self.q_network(states_batch, actions_batch)
        q_loss = F.mse_loss(current_q1, target_q) + F.mse_loss(current_q2, target_q)
        
        self.q_optimizer.zero_grad()
        q_loss.backward()
        self.q_optimizer.step()
        
        # 更新策略网络
        new_actions, log_probs, _ = self.policy.sample(states_batch)
        q1, q2 = self.q_network(states_batch, new_actions)
        q = torch.min(q1, q2)
        
        policy_loss = (self.alpha * log_probs - q).mean()
        
        self.policy_optimizer.zero_grad()
        policy_loss.backward()
        self.policy_optimizer.step()
        
        # 更新熵系数
        if self.auto_alpha_tuning:
            alpha_loss = -(self.log_alpha * (log_probs + self.target_entropy).detach()).mean()
            
            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()
            
            self.alpha = self.log_alpha.exp().item()
        
        # 软更新目标网络
        for target_param, param in zip(self.target_q_network.parameters(), self.q_network.parameters()):
            target_param.data.copy_(target_param.data * (1.0 - self.tau) + param.data * self.tau)
        
        return {
            'q_loss': q_loss.item(),
            'policy_loss': policy_loss.item()
        }
    

class CTDESACAgents:
    """集中式训练分散式执行的多智能体SAC系统"""
    def __init__(self, config):
        self.config = config
        self.device = config.AGENT_PARAMS['common']['device']
        
        self.agents = {}
        
        # 初始化电池智能体
        battery_params = config.AGENT_PARAMS['battery']
        self.agents['battery'] = SACAgent(
            state_dim=battery_params['state_dim'],
            action_dim=battery_params['action_dim'],
            agent_name='battery',
            hidden_dim=config.AGENT_PARAMS['common']['hidden_dim'],
            hidden_layers=config.AGENT_PARAMS['common']['hidden_layers'],
            lr_actor=config.AGENT_PARAMS['common']['lr_actor'],
            lr_critic=config.AGENT_PARAMS['common']['lr_critic'],
            gamma=config.AGENT_PARAMS['common']['gamma'],
            tau=config.AGENT_PARAMS['common']['tau'],
            alpha=config.AGENT_PARAMS['common']['alpha'],
            auto_alpha_tuning=config.AGENT_PARAMS['common']['auto_alpha_tuning'],
            device=self.device
        )
        
        # 初始化电解器智能体
        for i in range(config.PHYSICAL_PARAMS['electrolyzer']['count']):
            agent_name = f'electrolyzer_{i}'
            electrolyzer_params = config.AGENT_PARAMS['electrolyzer']
            self.agents[agent_name] = SACAgent(
                state_dim=electrolyzer_params['state_dim'],
                action_dim=electrolyzer_params['action_dim'],
                agent_name=agent_name,
                hidden_dim=config.AGENT_PARAMS['common']['hidden_dim'],
                hidden_layers=config.AGENT_PARAMS['common']['hidden_layers'],
                lr_actor=config.AGENT_PARAMS['common']['lr_actor'],
                lr_critic=config.AGENT_PARAMS['common']['lr_critic'],
                gamma=config.AGENT_PARAMS['common']['gamma'],
                tau=config.AGENT_PARAMS['common']['tau'],
                alpha=config.AGENT_PARAMS['common']['alpha'],
                auto_alpha_tuning=config.AGENT_PARAMS['common']['auto_alpha_tuning'],
                device=self.device
            )
        
        # 初始化经验回放缓冲区
        self.memory = ReplayBuffer(config.AGENT_PARAMS['common']['buffer_size'])
    
    def select_actions(self, observations, evaluate=False):
        """选择所有智能体的动作"""
        actions = []
        
        # 电池智能体动作
        battery_action = self.agents['battery'].select_action(
            observations['battery'], evaluate)
        actions.append(battery_action)
        
        # 电解器智能体动作
        for i in range(self.config.PHYSICAL_PARAMS['electrolyzer']['count']):
            electrolyzer_action = self.agents[f'electrolyzer_{i}'].select_action(
                observations[f'electrolyzer_{i}'], evaluate)
            actions.append(electrolyzer_action)
        
        return actions
    
    def update(self, batch_size, updates):
        """更新所有智能体"""
        results = {}
        
        # 更新电池智能体
        results['battery'] = self.agents['battery'].update_parameters(
            self.memory, batch_size, updates)
        
        # 更新电解器智能体
        for i in range(self.config.PHYSICAL_PARAMS['electrolyzer']['count']):
            results[f'electrolyzer_{i}'] = self.agents[f'electrolyzer_{i}'].update_parameters(
                self.memory, batch_size, updates)
        
        return results
    
    def save_models(self, path):
        """保存所有智能体模型"""
        for name, agent in self.agents.items():
            torch.save(agent.policy.state_dict(), f"{path}/{name}_policy.pth")
            torch.save(agent.q_network.state_dict(), f"{path}/{name}_q.pth")
    
    def load_models(self, path):
        """加载所有智能体模型"""
        try:
            print(f"正在加载模型路径: {path}")
            for name, agent in self.agents.items():
                policy_path = f"{path}/{name}_policy.pth"
                q_path = f"{path}/{name}_q.pth"
                
                if not os.path.exists(policy_path) or not os.path.exists(q_path):
                    print(f"警告: 模型文件不存在 - {policy_path} 或 {q_path}")
                    continue
                    
                print(f"加载智能体 {name} 的模型...")
                
                try:
                    policy_state_dict = torch.load(policy_path)
                    q_state_dict = torch.load(q_path)
                except RuntimeError as e:
                    if "CUDA" in str(e):
                        print(f"使用设备无关模式加载模型...")
                        policy_state_dict = torch.load(policy_path, map_location='cpu')
                        q_state_dict = torch.load(q_path, map_location='cpu')
                    else:
                        raise e
                
                try:
                    agent.policy.load_state_dict(policy_state_dict)
                    agent.q_network.load_state_dict(q_state_dict)
                    print(f"成功加载智能体 {name} 的模型")
                except Exception as e:
                    print(f"加载 {name} 模型时出错: {str(e)}")
                    print("尝试使用不严格模式加载...")
                    try:
                        agent.policy.load_state_dict(policy_state_dict, strict=False)
                        agent.q_network.load_state_dict(q_state_dict, strict=False)
                        print(f"使用不严格模式成功加载 {name} 模型")
                    except Exception as e2:
                        print(f"不严格模式加载 {name} 模型失败: {str(e2)}")
                        continue
                
                # 同步目标网络参数
                for target_param, param in zip(agent.target_q_network.parameters(), agent.q_network.parameters()):
                    target_param.data.copy_(param.data)
                
            print("模型加载完成")
        except Exception as e:
            print(f"加载模型时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e