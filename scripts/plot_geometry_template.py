"""Plot the limited-scope geometry-template experiment and its period grid."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    args = parser.parse_args()
    out = args.experiment
    destinations = [out/'geometry_template.png', out/'geometry_template.svg']
    if any(p.exists() for p in destinations):
        raise ValueError('Plot exists')
    joint = json.loads((out/'results.json').read_text(encoding='utf-8'))
    fixed = json.loads((out/'fixed_phase/results.json').read_text(encoding='utf-8'))
    audit = json.loads((out/'audit.json').read_text(encoding='utf-8'))
    if not joint.get('completed') or not fixed.get('completed') or not audit['hashes_unchanged']:
        raise ValueError('Completed, audited results required')
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False, 'font.size': 11})
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    labels = ['原单谐波', '经度相位修正', '完整模板\n联合局部拟合', '完整模板\n已知初始相位']
    values = [abs(joint['plain_error_s']), abs(joint['phase_error_s']), abs(joint['best']['error_s']), abs(fixed['error_s'])]
    bars = axes[0].bar(labels, values, color=['#5679a6', '#5c9c81', '#c28a5b', '#9468a8'])
    for bar, value in zip(bars, values):
        axes[0].text(bar.get_x()+bar.get_width()/2, value+.08, f'{value:.6f}', ha='center', fontsize=10)
    axes[0].set_ylabel('半周期绝对误差（秒）')
    axes[0].set_title('同一无噪声椭球作业；各模型先验不同')
    axes[0].set_ylim(0, max(values)*1.25)
    axes[1].semilogy(fixed['grid_period_s'], np.maximum(fixed['grid_sse'], 1e-20), '.-', color='#5679a6', label='32 Run 网格残差')
    axes[1].scatter([fixed['best_period_s']], [max(fixed['training_sse'], 1e-20)], color='#9468a8', label='局部细化结果', zorder=4)
    axes[1].axvline(fixed['reference_half_period_s'], color='#777777', linestyle='--', label='参考半周期（事后标注）')
    axes[1].set_xlabel('候选半周期（秒）')
    axes[1].set_ylabel('归一化残差平方和（对数轴）')
    axes[1].set_title('已知初始相位；连续区间全局最优未认证')
    axes[1].legend(fontsize=9)
    axes[1].ticklabel_format(axis='x', style='plain', useOffset=False)
    for ax in axes:
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle('更完整的几何模型能否提高半周期精度？', fontsize=15)
    for path in destinations:
        fig.savefig(path, dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    main()
