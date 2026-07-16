from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config
from environment import EnergySystemEnv


def main():
    env = EnergySystemEnv.__new__(EnergySystemEnv)
    env.physical_params = Config.PHYSICAL_PARAMS
    params = env.physical_params['wind_turbine']

    wind_speeds = np.linspace(0.0, 30.0, num=301)
    wind_powers = [env._calculate_wind_power(speed) for speed in wind_speeds]

    output_dir = PROJECT_ROOT / 'results'
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / 'wind_power_curve.png'

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(wind_speeds, wind_powers, linewidth=2, label='Wind power')
    for speed, label in (
        (params['cut_in_speed'], 'Cut-in'),
        (params['rated_speed'], 'Rated'),
        (params['cut_out_speed'], 'Cut-out'),
    ):
        ax.axvline(speed, linestyle='--', linewidth=1, label=f'{label}: {speed} m/s')

    ax.set(xlabel='Wind speed (m/s)', ylabel='Power (kW)')
    ax.set_xlim(0, 30)
    ax.set_ylim(0, params['rated_power'] * 1.05)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)

    print(output_path)


if __name__ == '__main__':
    main()
