# 风光储氢系统统一模型说明

> 版本：2026-07-15 光伏模型修订
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
| `P_dis,t` | `actual_discharge_power` | kW | 第 t 小时电池实际放电功率，非负 |

### 4.2 消纳侧

| 符号 | 代码字段或函数 | 单位 | 含义 |
|---|---|---:|---|
| `P_el,i,t` | `electrolyzer_powers[i]` | kW | 第 i 台电解槽第 t 小时实际耗电功率 |
| `P_ch,t` | `actual_charge_power` | kW | 第 t 小时电池实际充电功率，非负 |
| `P_curt,t` | `curtailment_power` | kW | 第 t 小时弃电功率，非负 |

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

电池内部已拆分为 `actual_charge_power` 和 `actual_discharge_power`。为兼容现有训练与结果脚本，`battery_power` 保留为实际净功率，定义为 `P_ch,t - P_dis,t`：正值表示充电，负值表示放电。

#### 4.3.1 7 月 17 日冻结、7 月 20 日实现的定义

> **状态说明：**本节于 2026-07-17 完成设计冻结；`requested_power_deficit`、`curtailment_power` 和 `power_balance_residual` 已按该定义于 2026-07-20 任务中实现。

```text
renewable_power
= wind_power + pv_power

available_power
= renewable_power + actual_discharge_power

requested_power_deficit
= max(0, requested_electrolyzer_power - available_power)

curtailment_power
= max(
    0,
    renewable_power
    + actual_discharge_power
    - actual_electrolyzer_power
    - actual_charge_power
)

power_balance_residual
= renewable_power
  + actual_discharge_power
  - actual_electrolyzer_power
  - actual_charge_power
  - curtailment_power
```

其中 `requested_electrolyzer_power` 和 `actual_electrolyzer_power` 分别表示所有电解槽请求功率与实际功率之和。`requested_power_deficit` 表示策略请求未被满足的部分，允许大于 0；`power_balance_residual` 表示实际执行是否守恒，正常情况下应在浮点容差内等于 0。平衡残差只用于检查，不得再加回电池以强制平衡。

充放电效率表示电池内部能量损耗，只进入 SOC 能量方程。上述瞬时母线侧功率平衡不再额外乘以效率，以避免重复计算损耗。

### 4.4 “策略请求—物理约束—实际执行”三层数据结构

| 层级 | 目标字段 | 含义 | 实现日期 |
|---|---|---|---|
| 策略请求 | `battery_action`、`requested_charge_power`、`requested_discharge_power`、`requested_electrolyzer_powers` | 保留策略原始意图，不保证可执行 | 电池部分已实现；统一接口 2026-07-23 |
| 物理约束 | `renewable_power`、SOC 可充放功率、额定功率、富余、缺额 | 记录请求被裁剪的物理原因 | 功率平衡字段已实现；统一分层输出 2026-07-23 |
| 实际执行 | `actual_charge_power`、`actual_discharge_power`、`actual_electrolyzer_powers`、`curtailment_power`、`requested_power_deficit`、`power_balance_residual`、`new_soc` | 表示真正进入状态转移和指标统计的结果 | 已实现；统一分层输出 2026-07-23 |

### 4.5 逐时历史与 episode 能源统计

环境按 1 小时时间步保存风光、充电、放电、电解槽、弃电、请求缺额和功率平衡残差历史，并累计对应能量。功率单位为 kW，累计能量单位为 kWh。全天统计满足：

```text
total_renewable_energy + total_discharge_energy
= total_electrolyzer_energy + total_charge_energy + total_curtailment_energy
```

`total_requested_power_deficit_energy` 是未满足请求的诊断累计量，不进入实际母线能量守恒方程。

## 5. 主要变量表

| 变量符号 | 当前代码字段 | 单位 | 含义 | 备注 |
|---|---|---:|---|---|
| `t` | `time_step` / `hour_idx` | h | 当前时间步或小时索引 | 一个 episode 共 24 步 |
| `v_t` | `wind_speed` | m/s | 第 t 小时风速 | 来自天气数据 |
| `G_t` | `light_intensity` | W/m2 | 第 t 小时有效辐照度 | CSV“光强”暂按有效辐照度使用，真实 GHI/POA 口径待核对 |
| `T_t` | `temperature` | degC | 第 t 小时环境温度 | 光伏模型中暂代组件温度 |
| `P_wind,t` | `wind_power` | kW | 风电输出功率 | 7 月 14 日修正风电公式 |
| `P_pv,t` | `pv_power` | kW | 调度环境可用光伏功率 | 7 月 15 日改为简化 PVWatts 型模型 |
| `SOC_t` | `self.soc` / `soc` | 无量纲 | 电池荷电状态 | 物理范围 0 到 1，推荐范围 0.2 到 0.8 |
| `P_ch,t` | `actual_charge_power` | kW | 电池实际充电功率 | 非负，已经供需、SOC、效率和额定功率裁剪 |
| `P_dis,t` | `actual_discharge_power` | kW | 电池实际放电功率 | 非负，已经供需、SOC、效率和额定功率裁剪 |
| `P_bat,t^req` | `requested_battery_power` | kW | 电池智能体请求的净功率 | 正值请求充电，负值请求放电 |
| `P_bat,t` | `actual_battery_power` / `battery_power` | kW | 电池实际净功率 | `P_ch,t - P_dis,t`，`battery_power` 为兼容字段 |
| `P_el,i,t` | `adjusted_electrolyzer_powers[i]` | kW | 第 i 台电解槽实际功率 | 当前 4 台同一最大/最小功率配置 |
| `H_t` | `hydrogen_produced` | Nm3 | 第 t 小时制氢量 | 当前由电解槽功率计算 |
| `H_total` | `total_hydrogen` | Nm3 | episode 累计制氢量 | 测试和评价指标使用 |
| `eta_consume,t` | `consumption_rate` | 无量纲 | 第 t 小时新能源消纳率 | 当前代码按逐小时比例计算 |
| `P_curt,t` | `curtailment_power` | kW | 弃电功率 | 已独立保存并累计为弃电量 |
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
| 光伏 | 参考辐照度 | 1000 | W/m2 | `pv.reference_irradiance` | NREL PVWatts | 否 |
| 光伏 | 参考温度 | 25 | degC | `pv.reference_temperature` | NREL PVWatts | 否 |
| 光伏 | 最大功率温度系数 | -0.0038 | 1/degC | `pv.temperature_coefficient` | NREL/CP-6A20-74097 标准组件代表值 | 是，待具体组件替换 |
| 电池 | 设备型号 | CATL EnerOne 1P，16 柜 | - | `battery.model` | CATL EnerOne 官方资料 | 否 |
| 电池 | 聚合额定能量 | 5963.2 | kWh | `battery.capacity` | 16 x 372.7 kWh | 否 |
| 电池 | 单柜额定电压 | 1331.2 | V | `battery.rated_voltage` | CATL EnerOne 官方资料，仅设备说明 | 否 |
| 电池 | 最大充电功率 | 5963.2 | kW | `battery.max_charge_power` | EnerOne 1P 聚合推算 | 否 |
| 电池 | 最大放电功率 | 5963.2 | kW | `battery.max_discharge_power` | EnerOne 1P 聚合推算 | 否 |
| 电池 | 充电效率 | 0.95 | 无量纲 | `battery.charge_efficiency` | 当前系统级建模假设 | 是，可调整 |
| 电池 | 放电效率 | 0.95 | 无量纲 | `battery.discharge_efficiency` | 当前系统级建模假设 | 是，可调整 |
| 电池 | 物理最小 SOC | 0.0 | 无量纲 | `battery.min_soc` | SOC 定义边界 | 否 |
| 电池 | 物理最大 SOC | 1.0 | 无量纲 | `battery.max_soc` | SOC 定义边界 | 否 |
| 电池 | 推荐 SOC 下限 | 0.2 | 无量纲 | `battery.recommended_min_soc` | LFP 推荐运行窗口建模设定 | 是，可调整 |
| 电池 | 推荐 SOC 上限 | 0.8 | 无量纲 | `battery.recommended_max_soc` | LFP 推荐运行窗口建模设定 | 是，可调整 |
| 电池 | 初始 SOC | 0.5 | 无量纲 | `battery.initial_soc` | 本项目典型日初始状态设定 | 是，可按实验调整 |
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
- EnerOne 单柜额定电压只用于设备说明。电池容量已以 kWh 表示，SOC 更新不再乘以电压。
- `charge_efficiency=0.95` 和 `discharge_efficiency=0.95` 不是 CATL 公开的 EnerOne 专属参数，而是当前可调整的系统级建模假设，往返效率为 90.25%。后续可根据 PCS 型号或实测数据替换。
- 电解槽 `recommended_power=150 kW` 小于 `min_power=250 kW`，当前含义不清，需要后续删除或重新解释。
- 制氢系数和固定项的单位口径当前不明确，后续应根据电解槽功率-制氢量模型统一核对。

## 7. 风力发电模型（2026-07-14）

### 7.1 分段功率曲线

风速输入 `v_t` 的单位为 m/s，风电输出 `P_wind,t` 和额定功率 `P_rated` 的单位均为 kW。为避免空气动力学公式输出 W、配置参数使用 kW 所造成的量纲混用，当前阶段采用额定功率归一化的分段三次曲线：

$$
P_{\text{wind},t} =
\begin{cases}
0, & v_t < v_{\text{ci}} \\
P_{\text{rated}} \cdot \dfrac{v_t^3 - v_{\text{ci}}^3}{v_{\text{r}}^3 - v_{\text{ci}}^3}, & v_{\text{ci}} \le v_t < v_{\text{r}} \\
P_{\text{rated}}, & v_{\text{r}} \le v_t \le v_{\text{co}} \\
0, & v_t > v_{\text{co}}
\end{cases}
$$

其中：

- `v_ci = 1 m/s`：切入风速；在该点输出为 0 kW。
- `v_r = 12 m/s`：额定风速；从该点起输出为额定功率。
- `v_co = 25 m/s`：切出风速；该点仍输出额定功率，超过该点后停机并输出 0 kW。
- `P_rated = 7000 kW`：风机组额定功率。

该模型是用于调度研究的静态简化模型，不考虑空气密度变化、湍流、尾流、偏航误差、机械与电气动态，也不使用叶片半径直接推算瞬时功率。配置中的 `blade_radius` 和 `air_density` 暂时保留用于参数溯源，但不参与当前功率曲线计算。

### 7.2 性质与边界约定

- 全风速范围内 `0 <= P_wind,t <= P_rated`。
- 在 `[v_ci, v_r]` 上功率严格单调增加。
- 在 `[v_r, v_co]` 上保持额定功率。
- 切出点右侧存在从额定功率到 0 的停机跳变，这是切出保护的简化表达。
- 0–30 m/s 功率曲线由 `scripts/plot_wind_power_curve.py` 生成，输出至 `results/wind_power_curve.png`。

### 7.3 完成标准自检

| 检查项 | 状态 | 验证方式 |
|---|---|---|
| 分段功率曲线和参数定义完整 | 完成 | 见 7.1 节 |
| 全范围输出不超过额定功率 | 完成 | `test_wind_power_stays_within_rated_power` |
| 切入至额定风速严格单调增加 | 完成 | `test_wind_power_is_strictly_increasing_between_cut_in_and_rated` |
| 切入、额定、切出及切出后边界正确 | 完成 | `test_wind_power_boundary_values` |
| 生成 0–30 m/s 功率曲线图 | 完成 | `results/wind_power_curve.png` |

## 8. 光伏发电模型（2026-07-15）

### 8.1 功率方程

光伏模型采用 NREL PVWatts 最大功率温度系数模型的简化形式。环境温度输入 `T_a,t` 的单位为 degC，有效辐照度输入 `G_t` 的单位为 W/m2，输出 `P_pv,t` 的单位为 kW：

$$
P_{\text{pv},t}^{\text{raw}}
= P_{\text{pv,r}}
\frac{G_t}{G_{\text{ref}}}
\left[1+\gamma_P(T_{a,t}-T_{\text{ref}})\right]
$$

$$
P_{\text{pv},t}
= \min\left(\max\left(P_{\text{pv},t}^{\text{raw}},0\right),P_{\text{pv,r}}\right)
$$

参数为：

- `P_pv,r = 5000 kW`：调度环境中的最大可用光伏功率。
- `G_ref = 1000 W/m2`：参考辐照度。
- `T_ref = 25 degC`：参考组件温度。
- `gamma_P = -0.0038 1/degC`：现代标准晶硅组件最大功率温度系数代表值。

基础方程参考 NREL《[PVWatts Version 5 Manual](https://docs.nrel.gov/docs/fy14osti/62641.pdf)》中的最大功率温度修正模型；温度系数采用 NREL/CP-6A20-74097《[Improvements to PVWatts for Fixed and One-Axis Tracking Systems](https://docs.nrel.gov/docs/fy19osti/74097.pdf)》给出的现代标准组件代表值 `-0.38 %/degC`。

### 8.2 建模口径与简化假设

1. PVWatts 原模型使用组件或电池片温度。当前数据仅提供环境温度，因此暂令 `T_cell,t ≈ T_a,t`。该假设通常低估白天组件升温，可能高估高辐照时段的光伏出力。
2. CSV 第三列仅标记为“光强”，当前直接作为有效辐照度 `G_t` 输入。其真实含义是水平面总辐照度 GHI、组件平面辐照度 POA，还是已经修正的有效辐照度，仍待核对。
3. `5000 kW` 定义为调度环境的最大可用光伏功率，不进一步区分 DC 铭牌容量、逆变器 AC 容量和并网侧净功率。
4. 当前不考虑组件倾角和方位角、入射角、光谱、遮挡、积灰、线路损失、逆变器效率、DC/AC 容量比及组件老化。
5. 当前模型服务于 1 h 时间步的风光储氢调度，不是完整 PVWatts、组件 I-V 模型或经过实测标定的电站模型。

### 8.3 边界与异常输入

- `G_t = 0` 时输出为 `0 kW`。
- `G_t < 0` 时抛出 `ValueError`，不静默修正无效天气数据。
- 温度或辐照度为 NaN、正无穷或负无穷时抛出 `ValueError`。
- 所有有效输入均满足 `0 <= P_pv,t <= 5000 kW`。
- 在温度固定时，输出随辐照度非递减；达到 5000 kW 后保持功率上限。
- 在未触及功率上下限时，由于 `gamma_P < 0`，相同辐照度下温度升高会使输出降低。

### 8.4 输入—输出检查表

在 `T_a = 25 degC` 时，温度修正因子为 1：

| 环境温度 | 有效辐照度 | 预期输出 |
|---:|---:|---:|
| 25 degC | 0 W/m2 | 0 kW |
| 25 degC | 200 W/m2 | 1000 kW |
| 25 degC | 500 W/m2 | 2500 kW |
| 25 degC | 1000 W/m2 | 5000 kW |
| 25 degC | 1200 W/m2 | 5000 kW（达到调度功率上限） |

在 `G_t = 500 W/m2` 时：

| 环境温度 | 温度修正因子 | 预期输出 |
|---:|---:|---:|
| -20 degC | 1.171 | 2927.5 kW |
| 0 degC | 1.095 | 2737.5 kW |
| 25 degC | 1.000 | 2500.0 kW |
| 40 degC | 0.943 | 2357.5 kW |

### 8.5 完成标准自检

| 检查项 | 状态 | 验证方式 |
|---|---|---|
| 功率方程、参数、单位和来源完整 | 完成 | 见 8.1 节 |
| 环境温度与有效辐照度简化口径已记录 | 完成 | 见 8.2 节 |
| 夜间输出为 0，输出位于额定范围 | 完成 | `test_pv_power_reference_points`、`test_pv_power_stays_bounded_over_project_weather_range` |
| 相同温度下随辐照度非递减 | 完成 | `test_pv_power_is_non_decreasing_with_irradiance` |
| 全年 8760 条天气记录无异常和越界 | 完成 | `test_pv_power_handles_all_annual_weather_records` |
| 负值、NaN 和 Inf 输入显式报错 | 完成 | 光伏异常输入测试 |

## 9. 电池模型（2026-07-16）

### 9.1 设备口径

当前电池原型为 16 柜 CATL EnerOne 1P 户外液冷 LFP 储能系统。单柜额定能量为 372.7 kWh，聚合额定能量为 5963.2 kWh。1P 口径下，最大充电和放电功率均取 5963.2 kW。产品信息来自 [CATL EnerOne 官方介绍](https://www.catl.com/en/news/935.html) 和 [CATL 储能产品手册](https://www.catl.com/en/uploads/1/file/public/202303/20230315092000_ahw9vpn63j.pdf)。

### 9.2 SOC 状态方程

时间步长 `Delta_t = 1 h`。充电和放电功率均定义在系统母线侧，SOC 更新为：

```text
SOC_(t+1) = SOC_t
            + eta_ch * P_ch,t * Delta_t / E_bat
            - P_dis,t * Delta_t / (eta_dis * E_bat)
```

当前 `eta_ch = eta_dis = 0.95`，是可调整的建模假设。额定电压不参与该能量方程。

### 9.3 请求动作与实际执行

电池动作范围为 `[-1, 1]`：正值请求充电，负值请求放电。实际充电功率取请求功率、当前风光富余、额定充电功率和 SOC 剩余空间四者的最小值。实际放电功率取请求功率、当前功率缺额、额定放电功率和 SOC 可用能量四者的最小值。

当请求方向与供需方向冲突时，实际电池功率为 0。零动作不得被后续功率平衡代码改写。`clip` 仅作为浮点边界误差的最后保护，不用来掩盖过大的充放电功率。

### 9.4 完成标准自检

| 检查项 | 状态 | 验证方式 |
|---|---|---|
| 容量不再重复乘以电压 | 完成 | SOC 充放电手算测试 |
| 充放电效率进入 SOC 方程 | 完成 | `test_one_hour_charge_matches_soc_equation` 和放电对应测试 |
| 动作能够改变下一时刻 SOC | 完成 | 电池动作、充电和放电测试 |
| SOC 上下限与功率上限生效 | 完成 | 边界与剩余容量裁剪测试 |
| 请求功率和实际功率分别保存 | 完成 | `step()` 输出和历史记录测试 |

## 10. 7 月 17 日电池验证与功率平衡设计冻结

### 10.1 当日定位与交付边界

2026-07-17 的工作性质是**验证与设计**，不是功率平衡的代码实现日。

| 当日状态 | 内容 |
|---|---|
| 已完成 | 电池测试结果核对、1 小时 SOC 手算、功率平衡公式、三层数据结构、四个人工场景预期表、SOC 双层边界设计 |
| 截至 7 月 17 日尚未实现 | 显式弃电、请求功率缺额、功率平衡残差、SOC 双层边界、推荐区间惩罚 |
| 后续日期 | 2026-07-20 实现功率平衡和物理 SOC 边界；2026-07-23 统一接口和诊断指标；2026-08-12 实现 SOC 推荐区间惩罚 |

因此，7 月 17 日任务勾选“完成”只表示上述验证和设计交付物已冻结，不表示设计中的所有字段均已进入代码。

### 10.2 电池测试与 1 小时手算核对

截至 2026-07-17，完整测试集为 33 项，全部通过，其中电池专项 13 项。电池专项已覆盖充电、放电、当时的 SOC 上下限、剩余容量功率裁剪、动作方向和请求/实际功率记录。完成 7 月 20 日任务后，测试集增至 39 项，新增物理 SOC 双层边界、四个人工功率场景和 24 小时能源统计验证。

| 场景 | 手算公式 | 预期 SOC | 测试结果 |
|---|---|---:|---|
| SOC 0.5，充电 1000 kW，1 h | `0.5 + 0.95 * 1000 / 5963.2` | 0.659310 | 通过 |
| SOC 0.5，放电 1000 kW，1 h | `0.5 - 1000 / (0.95 * 5963.2)` | 0.323479 | 通过 |

### 10.3 人工功率平衡场景预期表

> **实现状态：**下表于 2026-07-17 冻结，并已在 2026-07-20 任务中转为自动化测试；当前代码已输出表中功率平衡字段。

| 场景 | 风光功率 | 电解槽请求 | 电池请求 / SOC | 目标执行结果 |
|---|---:|---:|---|---|
| 无风无光 | 0 kW | 2000 kW | 0 kW / 0.5 | 电解槽实际 0 kW，请求缺额 2000 kW，弃电 0 kW |
| 刚好平衡 | 2000 kW | 2000 kW | 0 kW / 0.5 | 电解槽实际 2000 kW，请求缺额 0 kW，弃电 0 kW |
| 风光富余、电池未满 | 3000 kW | 2000 kW | 充电 1000 kW / 0.5 | 实际充电 1000 kW，弃电 0 kW，新 SOC 0.659310 |
| 风光富余、电池物理满电 | 3000 kW | 2000 kW | 充电 1000 kW / 1.0 | 实际充电 0 kW，弃电 1000 kW，SOC 保持 1.0 |

四个目标场景的 `power_balance_residual` 均应在浮点容差内等于 0。

### 10.4 SOC 双层边界：执行边界已实现

SOC 边界已拆分为物理硬边界 `[0, 1]` 和推荐运行区间 `[0.2, 0.8]`，初始 SOC 保持 0.5。执行层只禁止超出物理硬边界；推荐区间已进入配置，但尚未进入奖励函数。

```text
d_low  = max(0, (0.2 - SOC) / 0.2)
d_high = max(0, (SOC - 0.8) / 0.2)
soc_penalty = w_soc * (d_low^2 + d_high^2)
```

`w_soc` 不在 7 月 17 日确定，而是在 2026-08-12 奖励函数重构时与制氢、弃电、切换和波动分量统一标定。当前执行层已使用 `[0, 1]`，允许 SOC 在物理可行时进入推荐区间之外。

### 10.5 后续实施时间表

| 日期 | 实施内容 | 验收标准 |
|---|---|---|
| 2026-07-20 | 实现请求缺额、弃电、功率平衡残差和 SOC 物理硬边界 `[0,1]`；将四个人工场景转为自动化测试 | 逐小时残差为 0，满电时产生弃电，全天统计与逐时结果一致 |
| 2026-07-23 | 统一 `info` 中的策略请求、物理约束、实际执行和指标；增加 SOC 推荐区间偏离诊断量 | 每个字段都有单位和边界，环境不依赖具体策略 |
| 2026-07-24 | 运行功率平衡、SOC 硬边界、无风无光、富余功率和随机动作 24 h 集成测试 | 无 NaN、无 SOC 物理越界、无功率不守恒 |
| 2026-08-03 | 回归测试后冻结环境 V2 | 后续不再改变功率平衡公式和物理 SOC 边界 |
| 2026-08-11 | 清理 `agent.py` 中硬编码的 `0.2/0.8` 判断和电池动作偏置，使 SAC 使用环境公开参数 | 电池智能体动作实际影响对应设备，无隐藏边界常量 |
| 2026-08-12 | 将归一化二次 SOC 推荐区间惩罚接入奖励，确定 `w_soc` 并分开记录奖励分量 | 偏离越大惩罚越大，且数量级不淹没其他奖励项 |

## 11. 当前实现与后续修正提醒

7 月 13 日仅建立统一说明，不修改代码。根据当前代码状态，后续需要依次处理以下问题：

- 风电模型：已于 7 月 14 日改为分段三次功率曲线，输入为 m/s，输出统一为 kW。
- 光伏模型：已于 7 月 15 日改为简化 PVWatts 型功率模型；环境温度替代组件温度以及光强口径仍需在后续核对。
- 电池模型：已于 7 月 16 日口径下修正 SOC、效率、动作裁剪和请求/实际功率记录；0.95 的充放电效率后续可按 PCS 或实测数据调整。
- 功率平衡：已显式输出风光总功率、电解槽请求/实际总功率、请求缺额、弃电和平衡残差；逐时结果与 24 小时累计能源账本均满足守恒。统一分层接口仍按 2026-07-23 计划实施。
- 电解槽模型：当前 4 台电解槽共用一组功率上下限，后续改为 2 台碱性和 2 台 PEM 的逐台配置。

## 12. 7 月 13 日完成标准自检

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
