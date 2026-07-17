from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import Config
from environment import EnergySystemEnv


@pytest.fixture
def env():
    environment = EnergySystemEnv.__new__(EnergySystemEnv)
    environment.physical_params = Config.PHYSICAL_PARAMS
    return environment


@pytest.mark.parametrize(
    ("irradiance", "expected_power"),
    [(0.0, 0.0), (200.0, 1000.0), (500.0, 2500.0), (1000.0, 5000.0)],
)
def test_pv_power_reference_points(env, irradiance, expected_power):
    assert env._calculate_pv_power(25.0, irradiance) == pytest.approx(
        expected_power
    )


def test_pv_power_is_capped_at_dispatch_limit(env):
    assert env._calculate_pv_power(25.0, 1200.0) == 5000.0


def test_pv_power_is_non_decreasing_with_irradiance(env):
    irradiances = np.linspace(0.0, 1200.0, num=1201)
    powers = np.array(
        [env._calculate_pv_power(25.0, irradiance) for irradiance in irradiances]
    )

    assert np.all(np.diff(powers) >= 0.0)


def test_pv_power_decreases_as_temperature_increases(env):
    temperatures = [-20.0, 0.0, 25.0, 40.0]
    expected_powers = [2927.5, 2737.5, 2500.0, 2357.5]
    powers = [env._calculate_pv_power(temp, 500.0) for temp in temperatures]

    assert powers == pytest.approx(expected_powers)
    assert np.all(np.diff(powers) < 0.0)


def test_pv_power_stays_bounded_over_project_weather_range(env):
    temperatures = np.linspace(-24.34, 35.67, num=31)
    irradiances = np.linspace(0.0, 1017.3, num=101)
    rated_power = env.physical_params['pv']['rated_power']

    for temperature in temperatures:
        powers = np.array(
            [
                env._calculate_pv_power(temperature, irradiance)
                for irradiance in irradiances
            ]
        )
        assert np.all(np.isfinite(powers))
        assert np.all(powers >= 0.0)
        assert np.all(powers <= rated_power)


def test_pv_power_handles_all_annual_weather_records(env):
    project_root = Path(__file__).resolve().parents[1]
    data_path = project_root / 'data' / '风速-温度-光强-全年.csv'
    weather = pd.read_csv(data_path, header=None, encoding='utf-8-sig')
    rated_power = env.physical_params['pv']['rated_power']

    assert len(weather) == 8760
    for temperature, irradiance in weather.iloc[:, [1, 2]].itertuples(index=False):
        power = env._calculate_pv_power(temperature, irradiance)
        assert np.isfinite(power)
        assert 0.0 <= power <= rated_power


def test_pv_power_rejects_negative_irradiance(env):
    with pytest.raises(ValueError, match="non-negative"):
        env._calculate_pv_power(25.0, -0.1)


@pytest.mark.parametrize(
    ("temperature", "irradiance"),
    [
        (np.nan, 500.0),
        (np.inf, 500.0),
        (-np.inf, 500.0),
        (25.0, np.nan),
        (25.0, np.inf),
        (25.0, -np.inf),
    ],
)
def test_pv_power_rejects_non_finite_inputs(env, temperature, irradiance):
    with pytest.raises(ValueError, match="finite"):
        env._calculate_pv_power(temperature, irradiance)


def test_pv_power_accepts_single_element_numpy_inputs(env):
    power = env._calculate_pv_power(np.array([25.0]), np.array([500.0]))

    assert isinstance(power, float)
    assert power == pytest.approx(2500.0)
