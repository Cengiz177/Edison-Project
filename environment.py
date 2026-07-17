import numpy as np
import pandas as pd
from config import Config

class EnergySystemEnv:
    def __init__(self, mode='train'):
        self.config = Config()
        self.mode = mode
        self.physical_params = self.config.PHYSICAL_PARAMS
        
        self.current_theoretical_max_hydrogen = 0
        
        try:
            if mode == 'train':
                file_path = self.config.ENV_PARAMS['train_data_path']
            else:
                file_path = self.config.ENV_PARAMS['test_data_path']
                
            with open(file_path, 'r', encoding='utf-8') as f:
                data_lines = f.readlines()
            
            self.processed_data = []
            for line in data_lines:
                values = line.strip().split(',')
                if len(values) >= 3:
                    try:
                        first_val = values[0]
                        if first_val.startswith('\ufeff'):
                            first_val = first_val[1:]
                        
                        self.processed_data.append({
                            'wind_speed': float(first_val),
                            'temperature': float(values[1]),
                            'light_intensity': float(values[2])
                        })
                    except Exception as e:
                        print(f"解析行数据失败: {values}, 错误: {e}")
            
            if len(self.processed_data) < 24:
                print(f"警告：数据不足24小时，仅有 {len(self.processed_data)} 小时数据")
            
            self.data = pd.DataFrame(self.processed_data)
            
        except Exception as e:
            print(f"加载数据失败: {e}")
            print("警告：使用备用数据，这可能不适合正式评估！")
            self.data = pd.DataFrame({
                'wind_speed': [2.0] * 24,
                'temperature': [20.0] * 24,
                'light_intensity': [100.0] * 24
            })
        
        self.reset()
    
    def _to_scalar(self, value):
        if isinstance(value, np.ndarray):
            if value.size == 1:
                return float(value.item())
            else:
                return float(value[0])
        return float(value)
    
    def reset(self, hour_idx=None):
        if hour_idx is None and self.mode == 'train':
            total_hours = len(self.data)
            max_start_hour = total_hours - self.config.ENV_PARAMS['time_steps']
            start_hour = np.random.randint(0, max_start_hour)
            self.day_idx = start_hour // 24
            self.hour_idx = start_hour % 24
        elif hour_idx is None and self.mode == 'test':
            self.day_idx = 0
            self.hour_idx = 0
        else:
            total_hours = len(self.data)
            self.day_idx = hour_idx // 24
            self.hour_idx = hour_idx % 24
        
        self.time_step = 0
        
        self.soc = self.physical_params['battery']['initial_soc']
        self.total_hydrogen = 0
        self.switch_count = 0
        self.requested_battery_power_history = []
        self.battery_power_history = []
        self.electrolyzer_power_history = [[] for _ in range(4)]
        self.current_theoretical_max_hydrogen = 0
        
        self.last_battery_state = 0
        
        obs = self._get_observation()
        
        return obs
    
    def step(self, actions):
        battery_action = actions[0]
        electrolyzer_actions = actions[1:5]
        
        battery_power = self._scale_battery_action(battery_action)
        electrolyzer_powers = [self._scale_electrolyzer_action(a) for a in electrolyzer_actions]
        
        current_data = self._get_current_weather_data()
        
        wind_power = self._calculate_wind_power(current_data['wind_speed'])
        pv_power = self._calculate_pv_power(current_data['temperature'], current_data['light_intensity'])
        
        self.current_theoretical_max_hydrogen = self._calculate_theoretical_max_hydrogen(wind_power, pv_power)
        
        result = self._apply_physical_model(
            wind_power, pv_power, battery_power, electrolyzer_powers)
        
        hydrogen_produced = result['hydrogen_produced']
        consumption_rate = result['consumption_rate']
        new_soc = result['new_soc']
        adjusted_battery_power = result['adjusted_battery_power']
        requested_charge_power = result['requested_charge_power']
        requested_discharge_power = result['requested_discharge_power']
        actual_charge_power = result['actual_charge_power']
        actual_discharge_power = result['actual_discharge_power']
        adjusted_electrolyzer_powers = result['adjusted_electrolyzer_powers']
        adjusted_battery_power = self._to_scalar(adjusted_battery_power)
        
        current_battery_state = 0
        if adjusted_battery_power > 0:
            current_battery_state = 1
        elif adjusted_battery_power < 0:
            current_battery_state = -1
        
        new_switches = 0
        if self.last_battery_state * current_battery_state < 0 and self.last_battery_state != 0 and current_battery_state != 0:
            new_switches = 1

        
        self.last_battery_state = current_battery_state
        
        self.soc = new_soc
        self.total_hydrogen += hydrogen_produced
        self.switch_count += new_switches
        self.requested_battery_power_history.append(battery_power)
        self.battery_power_history.append(adjusted_battery_power)
        for i, p in enumerate(adjusted_electrolyzer_powers):
            self.electrolyzer_power_history[i].append(p)
        
        reward = self._calculate_reward(
            hydrogen_produced, consumption_rate, new_switches,
            adjusted_battery_power, adjusted_electrolyzer_powers)
        
        self.time_step += 1
        self.hour_idx += 1
        if self.hour_idx >= 24:
            self.hour_idx = 0
            self.day_idx = (self.day_idx + 1) % 365
        
        done = (self.time_step >= self.config.ENV_PARAMS['time_steps'])
        
        next_obs = self._get_observation()
        
        info = {
            'wind_power': wind_power,
            'pv_power': pv_power,
            'requested_battery_power': battery_power,
            'requested_charge_power': requested_charge_power,
            'requested_discharge_power': requested_discharge_power,
            'actual_charge_power': actual_charge_power,
            'actual_discharge_power': actual_discharge_power,
            'actual_battery_power': adjusted_battery_power,
            'battery_power': adjusted_battery_power,
            'electrolyzer_powers': adjusted_electrolyzer_powers,
            'hydrogen_produced': hydrogen_produced,
            'consumption_rate': consumption_rate,
            'soc': self.soc,
            'switch_count': new_switches,
            'total_switches': self.switch_count,
            'total_hydrogen': self.total_hydrogen,
            'theoretical_max_hydrogen': self.current_theoretical_max_hydrogen
        }
        
        return next_obs, reward, done, info
    
    def _get_observation(self):
        current_data = self._get_current_weather_data()
        
        rated_speed = max(0.1, self.physical_params['wind_turbine']['rated_speed'])
        
        rated_wind_power = self.physical_params['wind_turbine']['rated_power']
        rated_pv_power = self.physical_params['pv']['rated_power']
        ideal_total_power = rated_wind_power + rated_pv_power
        
        max_electrolyzer_capacity = self.physical_params['electrolyzer']['max_power'] * self.physical_params['electrolyzer']['count']
        ideal_electrolyzer_power = min(ideal_total_power, max_electrolyzer_capacity)
        
        current_wind_power = self._calculate_wind_power(current_data['wind_speed'])
        current_pv_power = self._calculate_pv_power(current_data['temperature'], current_data['light_intensity'])
        current_total_power = current_wind_power + current_pv_power
        
        wind_pv_excess_ratio = current_total_power / max_electrolyzer_capacity
        
        battery_soc_headroom = self.physical_params['battery']['max_soc'] - self.soc
        
        global_state = np.array([
            float(self.hour_idx) / 24.0,
            float(current_data['wind_speed']) / rated_speed,
            float(current_data['temperature']) / 100.0,
            float(current_data['light_intensity']) / 1000.0,
            float(self.soc),
            float(self.last_battery_state),
            float(self.switch_count) / 24.0,
            
            float(current_wind_power) / rated_wind_power,
            float(current_pv_power) / rated_pv_power,
            float(current_total_power) / ideal_total_power,
            
            float(wind_pv_excess_ratio),
            
            float(self.current_theoretical_max_hydrogen) / self._calculate_theoretical_max_hydrogen(rated_wind_power, rated_pv_power),
            
            float(battery_soc_headroom),
            
            float(max(0, wind_pv_excess_ratio - 1.0) * battery_soc_headroom * 3.0),
        ])
        
        observations = {}
        
        observations['battery'] = global_state
        
        for i in range(4):
            observations[f'electrolyzer_{i}'] = global_state
        
        return observations
    
    def _get_current_weather_data(self):
        idx = (self.day_idx * 24 + self.hour_idx) % len(self.data)
        
        if idx >= len(self.data):
            print(f"警告: 索引 {idx} 超出范围 (数据长度={len(self.data)})")
            
        return {
            'wind_speed': self.data.iloc[idx]['wind_speed'],
            'temperature': self.data.iloc[idx]['temperature'],
            'light_intensity': self.data.iloc[idx]['light_intensity']
        }
        
    def _calculate_wind_power(self, wind_speed):
        """Return wind-turbine power in kW for a wind speed in m/s.

        A normalized cubic curve is used between cut-in and rated speed.
        This avoids mixing the watt output of an aerodynamic formula with the
        configured rated power, which is expressed in kW.
        """
        params = self.physical_params['wind_turbine']

        wind_speed = self._to_scalar(wind_speed)
        cut_in_speed = params['cut_in_speed']
        rated_speed = params['rated_speed']
        cut_out_speed = params['cut_out_speed']
        rated_power = params['rated_power']

        if wind_speed < cut_in_speed or wind_speed > cut_out_speed:
            return 0.0
        if wind_speed < rated_speed:
            normalized_power = (
                (wind_speed ** 3 - cut_in_speed ** 3)
                / (rated_speed ** 3 - cut_in_speed ** 3)
            )
            return float(rated_power * normalized_power)
        return float(rated_power)
    
    def _calculate_pv_power(self, temperature, light_intensity):
        """Return dispatch-available PV power in kW.

        The model follows the basic PVWatts irradiance and temperature
        correction form. Ambient temperature is used as a documented proxy
        for cell temperature, and ``light_intensity`` is treated as effective
        irradiance in W/m2.
        """
        params = self.physical_params['pv']

        temperature = self._to_scalar(temperature)
        light_intensity = self._to_scalar(light_intensity)

        if not np.isfinite(temperature):
            raise ValueError(f"PV temperature must be finite, got {temperature}")
        if not np.isfinite(light_intensity):
            raise ValueError(
                f"PV effective irradiance must be finite, got {light_intensity}"
            )
        if light_intensity < 0:
            raise ValueError(
                f"PV effective irradiance must be non-negative, got {light_intensity}"
            )
        if light_intensity == 0:
            return 0.0

        temperature_factor = 1.0 + params['temperature_coefficient'] * (
            temperature - params['reference_temperature']
        )
        irradiance_ratio = light_intensity / params['reference_irradiance']
        raw_power = params['rated_power'] * irradiance_ratio * temperature_factor

        return float(np.clip(raw_power, 0.0, params['rated_power']))
    
    def _scale_battery_action(self, action):
        """Map a normalized action to requested net battery power in kW.

        Positive power requests charging and negative power requests
        discharging. Separate limits keep the mapping valid if the two ratings
        differ in a later equipment revision.
        """
        action = self._to_scalar(action)
        if not np.isfinite(action):
            raise ValueError(f"Battery action must be finite, got {action}")

        action = float(np.clip(action, -1.0, 1.0))
        params = self.physical_params['battery']
        if action >= 0.0:
            return action * params['max_charge_power']
        return action * params['max_discharge_power']
    
    def _scale_electrolyzer_action(self, action):
        max_power = self.physical_params['electrolyzer']['max_power']
        return action * max_power
    
    def _apply_physical_model(self, wind_power, pv_power, battery_power, electrolyzer_powers):
        wind_power = self._to_scalar(wind_power)
        pv_power = self._to_scalar(pv_power)
        battery_power = self._to_scalar(battery_power)
        electrolyzer_powers = [self._to_scalar(p) for p in electrolyzer_powers]
        
        elec_params = self.physical_params['electrolyzer']
        h2_params = self.physical_params['hydrogen_production']
        battery_params = self.physical_params['battery']
        
        min_soc = battery_params['min_soc']
        max_soc = battery_params['max_soc']
        battery_capacity = battery_params['capacity']
        max_charge_power = battery_params['max_charge_power']
        max_discharge_power = battery_params['max_discharge_power']
        charge_efficiency = battery_params['charge_efficiency']
        discharge_efficiency = battery_params['discharge_efficiency']
        time_step_hours = 1.0
        
        renewable_power = wind_power + pv_power
        
        adjusted_electrolyzer_powers = []
        for power in electrolyzer_powers:
            if power < elec_params['min_power']:
                adjusted_power = elec_params['standby_power']
            else:
                adjusted_power = min(power, elec_params['max_power'])
            adjusted_electrolyzer_powers.append(adjusted_power)
        
        requested_electrolyzer_power = sum(adjusted_electrolyzer_powers)

        requested_charge_power = max(0.0, battery_power)
        requested_discharge_power = max(0.0, -battery_power)

        renewable_surplus = max(
            0.0, renewable_power - requested_electrolyzer_power
        )
        renewable_deficit = max(
            0.0, requested_electrolyzer_power - renewable_power
        )

        soc_charge_limit = max(
            0.0,
            (max_soc - self.soc) * battery_capacity
            / (charge_efficiency * time_step_hours),
        )
        soc_discharge_limit = max(
            0.0,
            (self.soc - min_soc) * battery_capacity
            * discharge_efficiency / time_step_hours,
        )

        actual_charge_power = min(
            requested_charge_power,
            renewable_surplus,
            max_charge_power,
            soc_charge_limit,
        )
        actual_discharge_power = min(
            requested_discharge_power,
            renewable_deficit,
            max_discharge_power,
            soc_discharge_limit,
        )

        available_power_for_electrolyzers = (
            renewable_power + actual_discharge_power
        )
        if requested_electrolyzer_power > available_power_for_electrolyzers:
            if requested_electrolyzer_power > 0.0:
                reduction_factor = (
                    available_power_for_electrolyzers
                    / requested_electrolyzer_power
                )
                adjusted_electrolyzer_powers = [
                    power * reduction_factor
                    for power in adjusted_electrolyzer_powers
                ]

        total_electrolyzer_power = sum(adjusted_electrolyzer_powers)
        adjusted_battery_power = (
            actual_charge_power - actual_discharge_power
        )

        soc_change = (
            charge_efficiency * actual_charge_power * time_step_hours
            - actual_discharge_power * time_step_hours
            / discharge_efficiency
        ) / battery_capacity
        new_soc = self.soc + soc_change

        # Physical power limits should already keep SOC feasible. Clipping only
        # protects against floating-point noise at an exact boundary.
        new_soc = float(np.clip(new_soc, min_soc, max_soc))
        
        if renewable_power == 0:
            consumption_rate = 1.0
        else:
            consumed_renewable = min(
                renewable_power,
                total_electrolyzer_power + actual_charge_power,
            )
            consumption_rate = consumed_renewable / renewable_power
        
        hydrogen_produced = 0
        for i, power in enumerate(adjusted_electrolyzer_powers):
            if power > elec_params['min_power']:
                if i < 2:
                    hydrogen_produced += h2_params['linear_coef'] * (power / 1000)
                    hydrogen_produced += h2_params['fixed_consumption']
                else:
                    hydrogen_produced += (h2_params['nonlinear_coef_a'] * (power / 1000)**2 + 
                                        h2_params['nonlinear_coef_b'] * (power / 1000))
                    hydrogen_produced += h2_params['standby_consumption']
        
        hydrogen_produced = self._to_scalar(hydrogen_produced)
        consumption_rate = self._to_scalar(consumption_rate)
        new_soc = self._to_scalar(new_soc)
        adjusted_battery_power = self._to_scalar(adjusted_battery_power)
        
        adjusted_electrolyzer_powers_scalar = []
        for p in adjusted_electrolyzer_powers:
            adjusted_electrolyzer_powers_scalar.append(self._to_scalar(p))
        
        return {
            'hydrogen_produced': hydrogen_produced,
            'consumption_rate': consumption_rate,
            'new_soc': new_soc,
            'requested_battery_power': battery_power,
            'requested_charge_power': requested_charge_power,
            'requested_discharge_power': requested_discharge_power,
            'actual_charge_power': actual_charge_power,
            'actual_discharge_power': actual_discharge_power,
            'adjusted_battery_power': adjusted_battery_power,
            'adjusted_electrolyzer_powers': adjusted_electrolyzer_powers_scalar,
        }
    
    def _calculate_theoretical_max_hydrogen(self, wind_power, pv_power):
        wind_power = self._to_scalar(wind_power)
        pv_power = self._to_scalar(pv_power)
        
        elec_params = self.physical_params['electrolyzer']
        h2_params = self.physical_params['hydrogen_production']
        
        total_power = wind_power + pv_power
        
        max_electrolyzer_power = elec_params['max_power'] * elec_params['count']
        
        available_power = min(total_power, max_electrolyzer_power)
        
        if available_power < elec_params['min_power']:
            return 0
        
        linear_count = 2
        linear_max_power = linear_count * elec_params['max_power']
        linear_power = min(available_power, linear_max_power)
        linear_hydrogen = h2_params['linear_coef'] * (linear_power / 1000)
        
        nonlinear_count = elec_params['count'] - linear_count
        remaining_power = max(0, available_power - linear_power)
        
        nonlinear_hydrogen = 0
        if remaining_power > 0:
            nonlinear_power_per_unit = remaining_power / nonlinear_count
            if nonlinear_power_per_unit > elec_params['min_power']:
                nonlinear_hydrogen = nonlinear_count * (h2_params['nonlinear_coef_a'] * (nonlinear_power_per_unit / 1000)**2 + 
                                    h2_params['nonlinear_coef_b'] * (nonlinear_power_per_unit / 1000))
        
        total_hydrogen = linear_hydrogen + nonlinear_hydrogen
        if linear_power > 0:
            total_hydrogen += linear_count * h2_params['fixed_consumption']
        if remaining_power > 0:
            total_hydrogen += nonlinear_count * h2_params['standby_consumption']
        
        return total_hydrogen

    def _calculate_reward(self, hydrogen_produced, consumption_rate, switch_count, 
                    battery_power, electrolyzer_powers):
        hydrogen_produced = self._to_scalar(hydrogen_produced)
        consumption_rate = self._to_scalar(consumption_rate)
        switch_count = self._to_scalar(switch_count)
        battery_power = self._to_scalar(battery_power)
        electrolyzer_powers = [self._to_scalar(p) for p in electrolyzer_powers]
        
        weights = self.config.TRAIN_PARAMS['reward_weights']
        
        max_possible_hydrogen = self._to_scalar(self.current_theoretical_max_hydrogen)
        
        if max_possible_hydrogen > 0:
            h2_efficiency = hydrogen_produced / max_possible_hydrogen
            h2_reward = weights['hydrogen'] * h2_efficiency
        else:
            h2_reward = 0
        
        consumption_reward = weights['consumption'] * consumption_rate
        
        switch_penalty = weights['switching'] * switch_count
        
        soc_penalty = 0
        if self.soc < self.physical_params['battery']['min_soc'] or self.soc > self.physical_params['battery']['max_soc']:
            soc_penalty = 5.0
        
        h2_reward = self._to_scalar(h2_reward)
        consumption_reward = self._to_scalar(consumption_reward)
        switch_penalty = self._to_scalar(switch_penalty)
        soc_penalty = self._to_scalar(soc_penalty)
        
        reward = float(h2_reward + consumption_reward - switch_penalty - soc_penalty)
        
        return reward
