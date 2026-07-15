# 风光储氢系统统一模型说明

> 版本：2026-07-13 初稿  
> 目的：统一系统边界、变量、单位、功率流约定和现有参数口径，为后续物理模型修正、规则策略、MILP 和 SAC 实验提供共同定义。

## 1. 研究场景与系统边界

本项目研究离网风光储氢系统的日内调度优化。系统在 24 小时尺度内运行，每个 episode 包含 24 个时间步，时间步长为 1 h。

系统边界如下：

- 系统离网运行，不从外部电网购电，也不向外部电网售电。
- 风电和光伏是唯一外部电源。
- 电池用于跨时段转移电能，并受 SOC、容量和最大充放电功率约束。
- 电解槽消耗电能制氢，包括 2 台碱性电解槽和 2 台 PEM 电解槽。
- 当风光出力无法被电解槽和电池吸收时，允许产生弃电。
- 当前阶段不考虑储氢罐、氢负荷、售氢价格和外部电价。

## 2. 设备组成

| 设备 | 数量 | 当前建模作用 | 当前代码位置 |
|---|---:|---|---|
| 风机 | 1 组 | 提供风电功率输入 | `config.py` 的 `PHYSICAL_PARAMS['wind_turbine']`，`environment.py` 的 `_calculate_wind_power()` |
| 光伏 | 1 组 | 提供光伏功率输入 | `config.py` 的 `PHYSICAL_PARAMS['pv']`，`environment.py` 的 `_calculate_pv_power()` |
| 电池 | 1 组 | 充电、放电、SOC 状态转移 | `config.py` 的 `PHYSICAL_PARAMS['battery']`，`environment.py` 的 `_apply_physical_model()` |
| 碱性电解槽 | 2 台 | 基础制氢负荷，当前代码中对应电解槽 0 和 1 | `environment.py` 中 `i < 2` 的制氢计算分支 |
| PEM 电解槽 | 2 台 | 响应波动负荷，当前代码中对应电解槽 2 和 3 | `environment.py` 中 `i >= 2` 的制氢计算分支 |

## 3. 统一单位

| 物理量 | 单位 | 说明 |
|---|---|---|
| 功率 | kW | 风电、光伏、电池、电解槽、弃电均统一使用 kW |
| 能量 | kWh | 电池容量、逐小时电量统计使用 kWh |
| 时间 | h | 时间步长为 1 h |
| 制氢量 | Nm3 | 标准状态体积，后续报告中可写作 Nm³ |
| 风速 | m/s | 风电模型输入 |
| 辐照度 | W/m2 | 光伏模型输入，后续报告中可写作 W/m² |
| 温度 | degC | 光伏温度修正输入，后续报告中可写作 ℃ |
| SOC | 无量纲 | 取值范围为 0 到 1 |

说明：本文档文件本身优先使用 ASCII 兼容写法保存单位，例如 `Nm3`、`W/m2`、`degC`。报告或 PPT 中可以排版为 `Nm³`、`W/m²`、`℃`。

## 4. 功率流与正负号约定

为避免混用一个带正负号的电池功率变量，后续统一采用“充电功率”和“放电功率”分开表示的口径。

### 4.1 供给侧

| 符号 | 代码字段或函数 | 单位 | 含义 |
|---|---|---:|---|
| `P_wind,t` | `wind_power` | kW | 第 t 小时风电输出功率 |
| `P_pv,t` | `pv_power` | kW | 第 t 小时光伏输出功率 |
| `P_dis,t` | 后续建议新增；当前代码使用 `battery_power < 0` 表示 | kW | 第 t 小时电池实际放电功率，非负 |

### 4.2 消纳侧

| 符号 | 代码字段或函数 | 单位 | 含义 |
|---|---|---:|---|
| `P_el,i,t` | `electrolyzer_powers[i]` | kW | 第 i 台电解槽第 t 小时实际耗电功率 |
| `P_ch,t` | 后续建议新增；当前代码使用 `battery_power > 0` 表示 | kW | 第 t 小时电池实际充电功率，非负 |
| `P_curt,t` | 后续建议新增 | kW | 第 t 小时弃电功率，非负 |

### 4.3 功率平衡

统一功率平衡口径为：

```text
P_wind,t + P_pv,t + P_dis,t
= sum_i(P_el,i,t) + P_ch,t + P_curt,t
```

其中：

- `P_ch,t >= 0`
- `P_dis,t >= 0`
- `P_curt,t >= 0`
- 同一时间步内电池原则上不应同时充电和放电。

当前代码仍使用 `adjusted_battery_power` 表示电池功率，并以正值表示充电、负值表示放电。该变量只作为当前实现状态记录，后续重构时应拆分为 `actual_charge_power` 和 `actual_discharge_power`。

## 5. 主要变量表

| 变量符号 | 当前代码字段 | 单位 | 含义 | 备注 |
|---|---|---:|---|---|
| `t` | `time_step` / `hour_idx` | h | 当前时间步或小时索引 | 一个 episode 共 24 步 |
| `v_t` | `wind_speed` | m/s | 第 t 小时风速 | 来自天气数据 |
| `G_t` | `light_intensity` | W/m2 | 第 t 小时光照强度 | 来自天气数据 |
| `T_t` | `temperature` | degC | 第 t 小时环境温度 | 当前作为光伏模型温度输入 |
| `P_wind,t` | `wind_power` | kW | 风电输出功率 | 7 月 14 日修正风电公式 |
| `P_pv,t` | `pv_power` | kW | 光伏输出功率 | 7 月 15 日修正光伏公式 |
| `SOC_t` | `self.soc` / `soc` | 无量纲 | 电池荷电状态 | 当前范围 0.2 到 0.8 |
| `P_ch,t` | 当前未独立保存 | kW | 电池实际充电功率 | 后续从电池功率拆分 |
| `P_dis,t` | 当前未独立保存 | kW | 电池实际放电功率 | 后续从电池功率拆分 |
| `P_bat,t` | `adjusted_battery_power` | kW | 当前代码中的电池净功率 | 正值充电，负值放电，仅为当前实现口径 |
| `P_el,i,t` | `adjusted_electrolyzer_powers[i]` | kW | 第 i 台电解槽实际功率 | 当前 4 台同一最大/最小功率配置 |
| `H_t` | `hydrogen_produced` | Nm3 | 第 t 小时制氢量 | 当前由电解槽功率计算 |
| `H_total` | `total_hydrogen` | Nm3 | episode 累计制氢量 | 测试和评价指标使用 |
| `eta_consume,t` | `consumption_rate` | 无量纲 | 第 t 小时新能源消纳率 | 当前代码按逐小时比例计算 |
| `P_curt,t` | 当前未独立保存 | kW | 弃电功率 | 后续功率平衡重构中新增 |
| `N_switch` | `switch_count` / `total_switches` | 次 | 电池或设备切换次数 | 当前主要统计电池充放电方向切换 |

## 6. 参数核对表

| 模块 | 参数 | 当前值 | 单位 | 当前代码字段 | 来源 | 是否待核对 |
|---|---|---:|---|---|---|---|
| 风机 | 额定功率 | 7000 | kW | `wind_turbine.rated_power` | 现有配置 | 是 |
| 风机 | 切入风速 | 1 | m/s | `wind_turbine.cut_in_speed` | 现有配置 | 是 |
| 风机 | 额定风速 | 12 | m/s | `wind_turbine.rated_speed` | 现有配置 | 是 |
| 风机 | 切出风速 | 25 | m/s | `wind_turbine.cut_out_speed` | 现有配置 | 是 |
| 风机 | 叶片半径 | 68 | m | `wind_turbine.blade_radius` | 现有配置 | 是 |
| 风机 | 空气密度 | 1.205 | kg/m3 | `wind_turbine.air_density` | 现有配置 | 是 |
| 光伏 | 额定功率 | 5000 | kW | `pv.rated_power` | 现有配置 | 是 |
| 光伏 | 标准温度 | 25 | degC | `pv.standard_temp` | 现有配置 | 是 |
| 光伏 | 电压 | 250 | V | `pv.voltage` | 现有配置 | 是 |
| 电池 | 容量 | 6000 | kWh | `battery.capacity` | 现有配置 | 是 |
| 电池 | 当前代码电压参数 | 24 | V | `battery.voltage` | 现有配置 | 是 |
| 电池 | 最大充放电功率 | 6000 | kW | `battery.max_power` | 现有配置 | 是 |
| 电池 | 最小 SOC | 0.2 | 无量纲 | `battery.min_soc` | 现有配置 | 是 |
| 电池 | 最大 SOC | 0.8 | 无量纲 | `battery.max_soc` | 现有配置 | 是 |
| 电池 | 初始 SOC | 0.2 | 无量纲 | `battery.initial_soc` | 现有配置 | 是 |
| 电解槽 | 数量 | 4 | 台 | `electrolyzer.count` | 现有配置 | 是 |
| 电解槽 | 单台最大功率 | 2500 | kW | `electrolyzer.max_power` | 现有配置 | 是 |
| 电解槽 | 最小运行功率 | 250 | kW | `electrolyzer.min_power` | 现有配置 | 是 |
| 电解槽 | 推荐功率 | 150 | kW | `electrolyzer.recommended_power` | 现有配置 | 是 |
| 电解槽 | 待机功率 | 50 | kW | `electrolyzer.standby_power` | 现有配置 | 是 |
| 制氢 | 线性电解槽系数 | 205.31 | 待定 | `hydrogen_production.linear_coef` | 现有配置 | 是 |
| 制氢 | 非线性电解槽系数 a | -11.24 | 待定 | `hydrogen_production.nonlinear_coef_a` | 现有配置 | 是 |
| 制氢 | 非线性电解槽系数 b | 232.7 | 待定 | `hydrogen_production.nonlinear_coef_b` | 现有配置 | 是 |
| 制氢 | 固定消耗项 | 17.85 | 待定 | `hydrogen_production.fixed_consumption` | 现有配置 | 是 |
| 制氢 | 待机消耗项 | 8.89 | 待定 | `hydrogen_production.standby_consumption` | 现有配置 | 是 |

说明：

- 表中“来源”为“现有配置”的参数，仅说明它们来自当前代码，不代表已经完成物理合理性核对。
- 电池 `voltage` 参数当前参与 SOC 计算，但电池容量已经以 kWh 表示。后续电池模型修正时需要重点核对，避免容量重复乘以电压。
- 电解槽 `recommended_power=150 kW` 小于 `min_power=250 kW`，当前含义不清，需要后续删除或重新解释。
- 制氢系数和固定项的单位口径当前不明确，后续应根据电解槽功率-制氢量模型统一核对。

## 7. 当前实现与后续修正提醒

7 月 13 日仅建立统一说明，不修改代码。根据当前代码状态，后续需要依次处理以下问题：

- 风电模型：当前 `_calculate_wind_power()` 存在 W/kW 量纲混用风险，7 月 14 日改为分段功率曲线。
- 光伏模型：当前 `_calculate_pv_power()` 公式复杂且参数来源不清，7 月 15 日改为可解释的简化模型。
- 电池模型：当前 SOC 更新中存在容量再乘电压的问题，7 月 16 日修正。
- 功率平衡：当前用 `adjusted_battery_power` 兜底平衡，后续需要显式保存弃电和功率平衡残差。
- 电解槽模型：当前 4 台电解槽共用一组功率上下限，后续改为 2 台碱性和 2 台 PEM 的逐台配置。

## 8. 7 月 13 日完成标准自检

| 检查项 | 状态 | 说明 |
|---|---|---|
| 建立 `MODEL_SPEC.md` | 完成 | 本文件为初稿 |
| 写明系统边界 | 完成 | 见第 1 节 |
| 列出设备组成 | 完成 | 见第 2 节 |
| 统一单位 | 完成 | 见第 3 节 |
| 统一功率变量和正负号约定 | 完成 | 见第 4 节 |
| 主要变量有名称、单位和含义 | 完成 | 见第 5 节 |
| 参数整理为当前值、单位、来源、是否待核对 | 完成 | 见第 6 节 |
| 充电和放电不再用含糊的单一符号混合表示 | 完成 | 规范口径已拆分为 `P_ch,t` 和 `P_dis,t` |
