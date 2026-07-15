import numpy as np
import torch
import os
import time
from datetime import datetime
from config import Config
from environment import EnergySystemEnv
from agent import CTDESACAgents

def train():
    config = Config()
    env = EnergySystemEnv(mode='train')
    agents = CTDESACAgents(config)

    total_episodes = config.TRAIN_PARAMS['episodes']
    batch_size = config.AGENT_PARAMS['common']['batch_size']
    update_interval = config.TRAIN_PARAMS['update_interval']

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    save_dir = f"models/{timestamp}"
    os.makedirs(save_dir, exist_ok=True)

    episode_rewards = []
    hydrogen_production = []
    hydrogen_efficiency = []
    consumption_rates = []
    switch_counts = []
    
    # 新增：记录理论最大值为零的回合
    theoretical_max_is_zero = []

    window_size = 50
    best_avg_efficiency = 0
    best_single_efficiency = 0
    best_single_hydrogen = 0

    total_steps = 0
    for episode in range(total_episodes):
        observations = env.reset()
        episode_reward = 0
        episode_hydrogen = 0
        episode_theoretical_max = 0
        episode_consumption = 0
        episode_switches = 0
        episode_info = []

        for step in range(config.ENV_PARAMS['time_steps']):
            actions = agents.select_actions(observations)
            next_observations, reward, done, info = env.step(actions)
            episode_info.append(info)

            agents.memory.add(
                state=observations,
                action=actions,
                reward=float(reward) if isinstance(reward, np.ndarray) else reward,
                next_state=next_observations,
                done=done
            )

            observations = next_observations
            episode_reward += float(reward.item()) if isinstance(reward, np.ndarray) and reward.size == 1 else float(reward[0]) if isinstance(reward, np.ndarray) else reward

            if isinstance(info['hydrogen_produced'], np.ndarray):
                if info['hydrogen_produced'].size == 1:
                    episode_hydrogen += float(info['hydrogen_produced'].item())
                else:
                    episode_hydrogen += float(info['hydrogen_produced'][0])
            else:
                episode_hydrogen += info['hydrogen_produced']

            if isinstance(info['theoretical_max_hydrogen'], np.ndarray):
                if info['theoretical_max_hydrogen'].size == 1:
                    episode_theoretical_max += float(info['theoretical_max_hydrogen'].item())
                else:
                    episode_theoretical_max += float(info['theoretical_max_hydrogen'][0])
            else:
                episode_theoretical_max += info['theoretical_max_hydrogen']

            if isinstance(info['consumption_rate'], np.ndarray):
                if info['consumption_rate'].size == 1:
                    episode_consumption += float(info['consumption_rate'].item())
                else:
                    episode_consumption += float(info['consumption_rate'][0])
            else:
                episode_consumption += info['consumption_rate']

            if isinstance(info['switch_count'], np.ndarray):
                if info['switch_count'].size == 1:
                    episode_switches += int(info['switch_count'].item())
                else:
                    episode_switches += int(info['switch_count'][0])
            else:
                episode_switches += info['switch_count']
            total_steps += 1

            if len(agents.memory) > batch_size and total_steps % update_interval == 0:
                agents.update(batch_size, total_steps)

            if done:
                break

        episode_rewards.append(float(episode_reward) if isinstance(episode_reward, np.ndarray) else episode_reward)
        hydrogen_production.append(float(episode_hydrogen) if isinstance(episode_hydrogen, np.ndarray) else episode_hydrogen)

        # 修改：记录当前回合的效率并标记是否理论最大为零
        current_efficiency = 0
        if episode_theoretical_max > 0:
            current_efficiency = float(episode_hydrogen) / episode_theoretical_max
            hydrogen_efficiency.append(current_efficiency)
            theoretical_max_is_zero.append(False)  # 标记为有效回合
        else:
            hydrogen_efficiency.append(0)
            theoretical_max_is_zero.append(True)   # 标记为无效回合

        consumption_rates.append(float(episode_consumption / config.ENV_PARAMS['time_steps']))
        switch_counts.append(int(episode_switches) if isinstance(episode_switches, np.ndarray) else episode_switches)

        # 修改：计算平均效率时排除理论最大为零的回合
        window_start = max(0, episode - window_size + 1)
        valid_efficiencies = []
        
        # 只选取理论最大不为0的回合计算平均效率
        for idx in range(window_start, episode + 1):
            if idx < len(theoretical_max_is_zero) and not theoretical_max_is_zero[idx]:
                valid_efficiencies.append(hydrogen_efficiency[idx])
        
        # 计算有效回合的平均效率
        if valid_efficiencies:
            avg_efficiency = sum(valid_efficiencies) / len(valid_efficiencies)
            valid_ratio = len(valid_efficiencies) / (episode - window_start + 1)
        else:
            avg_efficiency = 0
            valid_ratio = 0

        if avg_efficiency > best_avg_efficiency:
            best_avg_efficiency = avg_efficiency
            best_model_dir = f"{save_dir}/best_model_avg_efficiency"
            os.makedirs(best_model_dir, exist_ok=True)
            agents.save_models(best_model_dir)
            print(f"保存新的最佳平均效率模型: 滑动窗口({window_size}回合)平均制氢效率 = {best_avg_efficiency:.4f} [有效回合比例: {valid_ratio:.2f}]")

        if current_efficiency > best_single_efficiency:
            best_single_efficiency = current_efficiency
            best_single_eff_dir = f"{save_dir}/best_model_single_efficiency"
            os.makedirs(best_single_eff_dir, exist_ok=True)
            agents.save_models(best_single_eff_dir)
            print(f"保存新的单回合最佳效率模型: 效率 = {best_single_efficiency:.4f}, 制氢量 = {episode_hydrogen:.2f} Nm³")

        if episode_hydrogen > best_single_hydrogen:
            best_single_hydrogen = episode_hydrogen
            best_single_h2_dir = f"{save_dir}/best_model_single_hydrogen"
            os.makedirs(best_single_h2_dir, exist_ok=True)
            agents.save_models(best_single_h2_dir)
            print(f"保存新的单回合最佳制氢量模型: 制氢量 = {best_single_hydrogen:.2f} Nm³, 效率 = {current_efficiency:.4f}")

        avg_consumption = episode_consumption / config.ENV_PARAMS['time_steps']
        soc_value = float(env.soc) if isinstance(env.soc, np.ndarray) else env.soc
        print(f"Episode {episode}/{total_episodes} - "
              f"Reward: {episode_reward:.2f}, "
              f"Hydrogen: {episode_hydrogen:.2f} Nm³, "
              f"H2 Efficiency: {current_efficiency:.4f}, "
              f"Switch Count: {episode_switches}, "
              f"Avg Consumption: {avg_consumption:.4f}, "
              f"SOC Start: {config.PHYSICAL_PARAMS['battery']['initial_soc']:.3f} ➜ End: {soc_value:.3f}, "
              f"Window({window_size}) Avg Eff: {avg_efficiency:.4f} [Valid: {valid_ratio:.2f}], "  # 添加有效率信息
              f"Best Avg Eff: {best_avg_efficiency:.4f}")

    # 保存训练数据
    try:
        np.savez(
            f"{save_dir}/training_data.npz",
            episode_rewards=episode_rewards,
            hydrogen_production=hydrogen_production,
            hydrogen_efficiency=hydrogen_efficiency,
            consumption_rates=consumption_rates,
            switch_counts=switch_counts,
            theoretical_max_is_zero=theoretical_max_is_zero
        )
        print(f"训练数据已保存至 {save_dir}/training_data.npz")
    except Exception as e:
        print(f"保存训练数据时出错: {e}")

    final_model_dir = f"{save_dir}/final"
    os.makedirs(final_model_dir, exist_ok=True)
    agents.save_models(final_model_dir)

    print("\n训练完成! 模型保存结果:")
    print(f"1. 最佳滑动窗口({window_size}回合)平均制氢效率: {best_avg_efficiency:.4f}")
    print(f"   模型路径: {save_dir}/best_model_avg_efficiency")
    print(f"2. 单回合最佳制氢效率: {best_single_efficiency:.4f}")
    print(f"   模型路径: {save_dir}/best_model_single_efficiency")
    print(f"3. 单回合最佳制氢量: {best_single_hydrogen:.2f} Nm³")
    print(f"   模型路径: {save_dir}/best_model_single_hydrogen")
    print(f"4. 最终模型")
    print(f"   模型路径: {save_dir}/final")

if __name__ == "__main__":
    try:
        print("开始执行训练脚本...")
        train()
    except Exception as e:
        print(f"训练主函数执行出错: {e}")
        import traceback
        traceback.print_exc()