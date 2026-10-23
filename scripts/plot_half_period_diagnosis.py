"""Render the frozen diagnosis result without re-running simulations."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    args=parser.parse_args()
    data=json.loads((args.input/'results.json').read_text(encoding='utf-8'))
    if not data.get('input_hashes_unchanged'):
        raise ValueError('Require a completed, hash-verified diagnosis')
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False})
    names=['total_power','centroid_delay_s','energy_width_90_s']
    labels=['总功率','质心时延','90% 能量宽度']
    conditions=[('actual','原始无噪回波','#0072B2'),
                ('phase_corrected','视线相位修正','#D55E00'),
                ('original_float64','双精度回波','#CC79A7'),
                ('fixed_los_float32','固定视线回波','#009E73')]
    fig,axes=plt.subplots(1,3,figsize=(13,4),constrained_layout=True)
    h=np.array([1,2,3,6])
    for ax,name,title in zip(axes,names,labels):
        for key,label,color in conditions:
            records=data[key] if key in ['actual','phase_corrected'] else data['controlled'][key]['estimates']
            if key=='phase_corrected' and any(records[f'{name}:H{order}']['dominant_harmonic']!=1 for order in h):
                raise ValueError('Half-period phase interpretation requires dominant harmonic one')
            error=[records[f'{name}:H{order}']['error_s'] for order in h]
            ax.plot(h,error,'o-',color=color,label=label,ms=4)
        ax.axhline(0,color='black',lw=.7)
        ax.set(title=title,xlabel='谐波阶数 H',ylabel='半周期偏差（秒）',xticks=h)
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.suptitle('目标半周期 5400 秒：固定作业的偏差诊断')
    for suffix in ['png','svg']:
        destination=args.input/f'half_period_bias.{suffix}'
        if destination.exists():
            raise ValueError(f'Refuse to overwrite {destination}')
        fig.savefig(destination,dpi=180,bbox_inches='tight')
    plt.close(fig)
    print(args.input/'half_period_bias.png')


if __name__=='__main__':
    main()
