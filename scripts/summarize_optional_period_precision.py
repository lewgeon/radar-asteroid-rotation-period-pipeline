"""Render the complete paired assessment without selecting results by truth."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    data = json.loads((args.output/'results.json').read_text(encoding='utf-8'))
    rows = data['records']
    names = ('total_power','centroid_delay_s','energy_width_90_s')
    lines = ['# 可选周期算法精度评估：2026-10-11','',
        '本说明冻结本次实验结果；后续结论追加到对应主题的独立阶段。生产算法和默认值均未修改。完整研究解释见 `docs/4.3/research/RADAR_PERIOD_ESTIMATION.md`。','',
        '## 条件与可复现命令','',
        '参考半周期 5400 s，全自转周期 10800 s；冻结的无噪声椭球、2000 个 singleton Run、全部 ADC 有效，观测跨度约 9.37 h。输入形状/初始相位不进入反演；视线补偿显式使用已知极轴 RA=105°、Dec=−66°。因此以下不是未知极轴或实测系统的精度保证。搜索范围 1800–14400 s，真值只参与搜索后的误差评价，未按真值挑选候选峰。','',
        f"测量时间：{data['created_utc']}；本次总耗时 {data['seconds']:.3f} s，搜索记录 {len(rows)} 条。输入 SHA256：`{data['input_sha256']}`。",'',
        '```powershell','conda activate pytorch',
        'python scripts/experiment_optional_period_precision.py --output tmp/optional_precision_20261011',
        'python scripts/summarize_optional_period_precision.py tmp/optional_precision_20261011',
        'python -m pytest tests/test_optional_period_precision.py tests/test_optional_period_methods.py -q',
        'python scripts/check_doc_math.py','```','',
        '原始 JSON/图放忽略的 `tmp/optional_precision_20261011/`；目录必须尚不存在，重建时换新的输出目录。这里的误差表完整列出参与比较的配置，不依据真值筛选最优结果。一次性数据未放入发布档案，固定脚本和输入哈希允许复核。','',
        '## 4000 网格无噪声误差','',
        '所有数字为估计半周期减 5400 s，有符号；末位小数仅方便复核。表中功率/质心/宽度分别独立估计，未做自动择优或联合融合。','',
        '| 补偿 | H | 细化 | 功率误差/s | 质心误差/s | 宽度误差/s |',
        '| --- | --- | --- | --- | --- | --- |']
    for p in (False,True):
        for h in (1,2):
            for r in (False,True):
                selected = [next(x for x in rows if x['stage']=='grid' and x['grid']==4000 and
                    x['phase']==p and x['harmonics']==h and x['refine']==r and x['feature']==n) for n in names]
                lines.append(f"| {int(p)} | {h} | {int(r)} | "+' | '.join(f"{x['error_s']:+.6f}" for x in selected)+' |')
    lines += ['', '## 网格稳定性：距离质心','',
        '| 补偿 | H | 细化 | G4000误差/s | G8000误差/s | G16000误差/s |',
        '| --- | --- | --- | --- | --- | --- |']
    for p in (False,True):
        for h in (1,2):
            for r in (False,True):
                selected = [next(x for x in rows if x['stage']=='grid' and x['grid']==g and
                    x['phase']==p and x['harmonics']==h and x['refine']==r and x['feature']==names[1]) for g in (4000,8000,16000)]
                lines.append(f"| {int(p)} | {h} | {int(r)} | "+' | '.join(f"{x['error_s']:+.6f}" for x in selected)+' |')
    lines += ['','细化减少离散网格对同一模型最优值的限制，不保证更接近物理真值。粗网格偶然更接近真值只能说明该网格的离散误差与连续拟合偏差抵消，不能据此独立确认偏差的物理来源。多谐波改变模型；拟合分数变高也不保证周期准确度提高。','',
        '## 配对原始 IQ 接收噪声','',
        'ADC 窗平均信号/噪声功率比 40/20 dB，复高斯白噪声，每档 3 种固定随机种子。同一含噪 IQ 用于补偿×H 的四组合；固定细化开启、G4000。不是特征 SNR 或脉压峰值 SNR。各 Run 只有一行且无样点重复计权，因此可独立逐行加噪。该阶段没有比较关闭细化。','',
        'RMSE 包含相对真值的偏差与随机波动；标准差使用 ddof=1，三次重复不足以形成可靠置信区间或尾部风险结论。','',
        '| 特征 | SNR/dB | 补偿 | H | 平均误差/s | 标准差/s | RMSE/s |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for n in names:
        for snr in (40.,20.):
            for p in (False,True):
                for h in (1,2):
                    errors = np.array([x['error_s'] for x in rows if x['stage']=='noise' and x['feature']==n and
                        x['snr_db']==snr and x['phase']==p and x['harmonics']==h])
                    assert len(errors)==3
                    lines.append(f"| {n} | {snr:g} | {int(p)} | {h} | {errors.mean():+.6f} | {errors.std(ddof=1):.6f} | {np.sqrt(np.mean(errors**2)):.6f} |")
    lines += ['','## 极轴敏感性','',
        '分别扰动 RA 或 Dec，另一坐标不变；H=1、细化开启、G4000、无噪声。这里只评价补偿使用了错误极轴时的结果，不是极轴联合反演或统计不确定度。','',
        '| 极轴参数 | 偏差/deg | 功率误差/s | 质心误差/s | 宽度误差/s |',
        '| --- | --- | --- | --- | --- |']
    for key in ('spin_axis_ra_deg','spin_axis_dec_deg'):
        for delta in (-5.,-1.,1.,5.):
            selected = [next(x for x in rows if x['stage']=='pole' and x['pole_parameter']==key and
                x['pole_error_deg']==delta and x['feature']==n) for n in names]
            lines.append(f"| {key} | {delta:+g} | "+' | '.join(f"{x['error_s']:+.6f}" for x in selected)+' |')
    lines += ['','## 证据范围','',
        '新增三项测试检查加噪可复现性、功率约定、输入不变、非法重复行拒绝以及合成数据对补偿/谐波/细化的敏感性；既有可选算法测试保留八组合独立回归与冻结 golden。此轮只修改研究脚本和文档，未重复验收所有 GUI/CW 入口，也不声称其发生新变化。对抗性审查需独立读取结果表后再确认交付。','',
        '未评估：一般不对称形状、多脉冲重叠 ADC 加噪、实际标定误差、相关/非高斯噪声、未知极轴联合求解、文献 APT/GP/PDM 的实际复现。本轮不以单场景结果改变默认值或宣布精度上限。','',
        '算法及实验源码 SHA256：','']
    lines += [f'- `{k}`：`{v}`' for k,v in data['source_hashes'].items()]
    (args.output/'assessment.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    fig, axes = plt.subplots(1,3,figsize=(12,3.6),constrained_layout=True)
    for ax,n in zip(axes,names):
        for p in (False,True):
            for h in (1,2):
                chosen = sorted([x for x in rows if x['stage']=='grid' and x['feature']==n and
                    x['refine'] and x['phase']==p and x['harmonics']==h],key=lambda x:x['grid'])
                ax.plot([x['grid'] for x in chosen],[x['error_s'] for x in chosen],marker='o',label=f'phase={int(p)}, H={h}')
        ax.axhline(0,color='gray',linewidth=.7)
        ax.set(title=n,xlabel='Frequency grid count',ylabel='Half-period error (s)')
    axes[0].legend(fontsize=7)
    fig.savefig(args.output/'refined_grid_errors.png',dpi=180)
    plt.close(fig)

if __name__=='__main__':
    main()
