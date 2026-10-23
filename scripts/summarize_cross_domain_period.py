# -*- coding: utf-8 -*-
"""Render frozen first-round evidence; never choose models from reference error."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
NAMES={'centroid':'距离质心','profile_power':'距离功率像','profile_shape':'归一化距离像'}

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
        ['| '+' | '.join(map(str,r))+' |' for r in rows])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--base',type=Path,required=True)
    p.add_argument('--extension',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    if a.report.exists():
        raise FileExistsError('Use a new report path; frozen evidence must not be overwritten')
    b=json.loads(a.base.read_text(encoding='utf-8'))
    e=json.loads(a.extension.read_text(encoding='utf-8'))
    if any(e['source_hashes'][k]!=v for k,v in b['source_hashes'].items()):
        raise ValueError('Shared dependencies differ')
    br,er=b['records'],e['records']
    clean=[]
    for name in NAMES:
        for phase in (False,True):
            initial=next(r for r in br if r['stage']=='selected' and r['representation']==name and r['phase']==phase)
            extended=next(r for r in er if r['stage']=='extended_selected' and r['representation']==name and r['phase']==phase)
            clean.append([NAMES[name], '开' if phase else '关',f"{initial['error_s']:+.6f}",f"{extended['error_s']:+.6f}",
                f"{initial['cv_mse']:.6f}",f"{extended['cv_mse']:.6f}"])
    noise=[]
    for family,records,stage,method in [('基础',br,'noise','H1'),('初轮样条',br,'noise','spline'),('扩展样条',er,'extended_noise',None),('抽样核',br,'noise','kernel')]:
        for name in (('centroid',) if family=='基础' else NAMES):
            errs=np.array([r['error_s'] for r in records if r['stage']==stage and r['phase'] and r['representation']==name and (method is None or r['method']==method)])
            if len(errs)!=5:
                raise ValueError('Five paired seeds required')
            noise.append([family,NAMES[name],f'{errs.mean():+.6f}',f'{errs.std(ddof=1):.6f}',f'{np.sqrt(np.mean(errs**2)):.6f}'])
    origins=[]
    bins=[]
    for family in ('initial','extended'):
        rr=[r for r in er if r['stage']=='origin' and r['phase'] and r['representation']=='profile_shape' and r['family']==family]
        origins.append([family]+[f"{r['error_s']:+.6f}" for r in rr])
        rr=[r for r in er if r['stage']=='bins' and r['phase'] and r['representation']=='profile_shape' and r['family']==family]
        bins.append([family]+[f"{r['error_s']:+.6f}" for r in rr])
    kernels=[]
    for name in ('centroid','profile_shape'):
        for count in (40000,160000,1999000):
            rr=[r for r in er if r['stage']=='controlled_kernel' and r['representation']==name and r['pairs']==count]
            kernels.append([NAMES[name],count,', '.join(f"{r['error_s']:+.6f}" for r in rr)])
    synthetic=[[r['truth_s'],r['regime'],f"{r['error_s']:+.9f}"] for r in br if r['stage']=='synthetic']
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(11,4.3),constrained_layout=True)
    for family,label in [('initial','32结点'),('extended','64结点')]:
        rr=[r for r in er if r['stage']=='origin' and r['phase'] and r['representation']=='profile_shape' and r['family']==family]
        axes[0].plot([r['knot_fraction'] for r in rr],[r['error_s'] for r in rr],'o-',label=label)
        rr=[r for r in er if r['stage']=='bins' and r['phase'] and r['representation']=='profile_shape' and r['family']==family]
        axes[1].plot([r['bins'] for r in rr],[r['error_s'] for r in rr],'o-',label=label)
    for ax in axes:
        ax.axhline(0,color='gray',lw=1)
        ax.axhline(1.596767,color='black',ls='--',lw=1,label='质心 H=1＋视线补偿')
        ax.set_ylabel('半周期估计偏差 / s')
        ax.grid(alpha=.2)
    axes[0].set_xlabel('结点原点平移 / 结点间距')
    axes[1].set_xlabel('距离像中央箱数量')
    axes[0].legend(fontsize=9)
    image_dir=a.report.parent/f'{a.report.stem}_figures'
    image_dir.mkdir(parents=True,exist_ok=True)
    for suffix in ('png','svg'):
        fig.savefig(image_dir/f'2026-10-11_STABILITY.{suffix}',dpi=180)
    plt.close(fig)
    text=f'''# 无形状真值周期估计第一轮实验（2026-10-11）

在这一冻结场景中，从数据学习距离像周期关系观察到了小于 1 秒的单次偏差，但稳定性检查没有支持“已获得可靠亚秒精度”的结论。初轮五块留出选择的归一化距离像样条偏差为 +0.831299 s；扩展结点扫描后，留出误差降低，周期偏差却变为 −1.908605 s，移动结点原点还会改变结果。核相似性方法也对配对抽样敏感。应继续研究模型偏差，暂不接入生产默认算法或 GUI 精度选项。

## 1. 输入、先验与比较范围

输入为 `runs/paras_for_70m_3h/echo/echo.npz`，SHA256 为 `{b['input_sha256']}`。目标真实自转周期 10800 s，评价参考为椭球重复半周期 5400 s；参考值仅用于生成独立数学夹具和事后评价，不传入搜索或超参数选择。2000 个单脉冲 Run、约 9.37 小时时间跨度约覆盖 6.25 个半周期，Chirp 带宽 150 MHz、脉宽 50 μs、ADC 200 MHz。本轮保持所有 2000 行，不裁剪规模。

没有向新反演方法提供形状模型、面元、散射参数或初始自转相位。视线补偿明确使用已知极轴 RA=105°、Dec=−66°，因此结论限于已知极轴场景。观测时间、视线几何和采集路径窗属于可用观测元数据，不等同于未知形状真值。当前输入是一个无噪声椭球仿真场景；不能据此保证未知极轴、一般形状或真实系统的精度。

基础算法用距离质心 H=1 在 1800–14400 s 盲搜，随后新方法在该数据候选的 ±2% 区间局部细化。五块留出每折重新拟合周期和系数，归一尺度只由训练集计算，但候选范围来自全数据基础算法；这是候选条件下的预测检验，不是全流程独立外推验证。补偿关闭/开启的基础半周期分别为 5404.493480 / 5401.596767 s，偏差分别为 +4.493480 / +1.596767 s。

## 2. 实际比较的两条路线

周期样条把距离质心或距离像视为未知的光滑周期函数，搜索周期并拟合其系数，不改变发射 Chirp。这里学习的是回波特征随自转相位的变化，不是发射信号波形。距离像来自完整原生脉压相关功率，经样点单元积分映射到固定延迟箱；定义 D 为元数据 planned_target_extent_path_m 给出的 300 m 采集路径窗，c 为光速；±D/c 内有 64 个中央箱，两侧各保留一个尾箱，逐行总功率守恒。归一化距离像再除以该行总功率；未使用形状确定的门限，也未使用跨 Run 载波相位。

样条初轮扫描 8/16/32 结点和循环二阶差分惩罚 0.001/0.1/10；按五块留出均方误差选择，各表示均选中 32 结点、惩罚 0.1。因选择命中扫描上边界，按预声明协议扩展到 64 结点，同样按留出误差选择，均选中 64 结点、惩罚 0.1。扩展后仍命中边界，因此不能宣称结点选择已收敛。没有按最接近 5400 s 的配置挑结果。

核方法借鉴 [CKP 原始论文](https://arxiv.org/abs/1212.2398)，比较真实时间差与距离像相似性所形成的周期重复关系。本轮是 CKP 思想迁移，不是原论文完整复现。研究预设相位核宽度 0.5，另保留 0.2/1 扫描；观测对不是独立样本，不能把近 200 万对解释成近 200 万次观测。

## 3. 无噪声结果：预测误差不等于周期准确度

下表为有符号半周期误差，单位秒。留出误差使用各表示自身的训练尺度，不能跨表示直接比较数值大小；它只用于同一表示内部选择结点和惩罚。

{table(['表示','视线补偿','初轮 K32 偏差/s','扩展 K64 偏差/s','初轮留出 MSE','扩展留出 MSE'],clean)}

归一化距离像初轮达到 +0.831299 s，而只对质心提高模型自由度，相对基础 H=1 未改善无噪声准确度。扩展 K64 后，各表示留出误差都降低，但补偿后的归一化距离像真值误差反而增大。数据中的慢变几何、散射和表示变化并不一定服从单一平稳周期函数，预测拟合能改善而周期仍偏离。

## 4. 结点原点与距离像分辨率

保持归一化距离像、开启视线补偿，平移周期样条结点原点，不改变数据、几何或真实周期：

{table(['模型','0 间距','0.25 间距','0.5 间距','0.75 间距'],origins)}

这不是要求已知初始自转相位。自由系数已经学习周期曲线的位置；有限结点及正则化会使数值模型依赖结点网格原点，这是算法表示造成的敏感性。不得选中最接近真值的原点作为精度成果。

保持结点原点和同一组留出选定参数，改变中央箱数，两侧尾箱始终保留：

{table(['模型','64 箱','128 箱','256 箱','512 箱'],bins)}

分辨率会改变距离像特征的计权与近似，结果未单调趋向真值。不能把 128 箱的较小误差当作已经找到最佳分辨率，也不能把 32 结点优于 64 结点当作通用默认值依据。

![归一化距离像的结点与表示敏感性](<{quote(image_dir.name)}/2026-10-11_STABILITY.png>)

## 5. 核方法：控制带宽和搜索网格后的配对敏感性

初轮抽样与全配对比较同时改变了配对距离中位数和搜索网格，故追加控制实验：全部使用 81 点初始网格加连续细化，绝对幅度核宽度固定为全配对距离中位数，相位核宽度固定 0.5，视线补偿开启。抽样种子为 20261011/20261111/20261211，全配对仅运行一次。

{table(['表示','观测对数量','三个抽样种子或全配对的偏差/s'],kernels)}

抽样恰好接近真值不能代替全配对参考。当前核目标没有证明稳定优于基础 H=1；需要先解决目标函数的偏差和抽样误差，不能直接包装成精度提升开关。

## 6. 相同原始 IQ 噪声的重复比较

20 dB 表示对完整 clean IQ 全体样点平均功率定义的白噪声 SNR，不是目标支撑区间 SNR 或脉压后 SNR。种子为 20261021–20261025，每个种子的相同复白噪声 IQ 用于所有算法，重新脉压、提取特征和盲搜基础候选；样条参数冻结为无噪声留出选择，不根据含噪真值调参。数据全部为无共享 ADC 行的单脉冲 Run，独立行噪声仅在该条件下合法。

{table(['算法','表示（视线补偿开）','平均偏差/s','样本标准差/s','RMSE/s'],noise)}

归一化距离像对本轮白噪声的波动较小，但重复性与准确度不同：64 结点模型可以稳定地偏离真值。五个种子只作探索，不能据此给出可靠置信区间，也没有覆盖有色噪声、时钟误差或轨道误差。

表中抽样核来自主实验：固定 160000 个配对、种子 20261011、相位核宽度 0.5、网格 81，幅度宽度按每组含噪数据的配对距离中位数重新计算。它与第 5 节固定绝对幅度宽度的无噪声控制实验不同。归一化距离像抽样核的含噪亚秒偏差不能推翻全配对 +2.580187 s 及换抽样种子后变化的结果；本轮未进行全配对含噪重复实验。

## 7. 独立数学夹具：数值精度与模型错配

在实际观测时刻上构造未知非正弦函数 exp(1.2 cos φ)+0.3 sin(3φ+0.4)，周期分别为 3600/5400/7200 s。反演仅收到时刻、函数值和对应已知相位扰动，基础算法提供候选，样条固定 32 结点、惩罚 0.001；无真值搜索窗口。慢变幅度条件额外乘以从 1 到 1.08 的线性因子。该夹具验证数学恢复，不是重新生成自洽天体回波。

{table(['参考周期/s','条件','偏差/s'],synthetic)}

平稳和已知相位扰动夹具可以远小于 1 秒；加入仅 8% 的幅度漂移后出现秒级偏差。这说明当前秒级结果不能称为普遍物理极限，也不能仅靠缩小周期网格解决。几何变化下的非平稳特征模型仍是重要研究方向。

## 8. 验证、证据与复现

主实验完成 {len(br)} 条结果，记录时间 `{b['created_utc']}`，耗时 {b['seconds']:.3f} s；扩展完成 {len(er)} 条结果，记录时间 `{e['created_utc']}`，耗时 {e['seconds']:.3f} s。二者共享依赖哈希完全相同；脚本启动冻结源码哈希，保存时拒绝源码或基线变化。原始 JSON 在忽略的 tmp 中，本文件保留结果、协议与可重建命令。首次主实验输出仍保留；修正哈希记录后进行了全量重跑，未更换算法或挑选噪声结果。

测试覆盖独立增广最小二乘参照、样条周期性、已知相位扰动、分别改变结点/惩罚、训练尺度不读取留出值、独立样点积分 golden、功率守恒、核抽样可重复及常数相位抵消。研究估计器与既有可选方法测试合计 32 项通过。正惩罚、非退化训练集和局部候选是本轮合法输入范围；不声明零惩罚稀疏相位覆盖、所有形状或所有采样都适用。

在仓库根目录执行，三个输出目录均须不存在：

```powershell
conda activate pytorch
python scripts/experiment_cross_domain_period.py --output tmp/cross_domain_period_20261011_reviewed
python -m scripts.experiment_cross_domain_stability --base tmp/cross_domain_period_20261011_reviewed/results.json --output tmp/cross_domain_period_20261011_stability_reviewed
python scripts/summarize_cross_domain_period.py --base tmp/cross_domain_period_20261011_reviewed/results.json --extension tmp/cross_domain_period_20261011_stability_reviewed/results.json --report tmp/cross_domain_period_reproduction.md
python -m pytest tests/test_research_period_estimators.py tests/test_optional_period_methods.py -q
python scripts/check_doc_math.py
```

复现会生成新的研究证据；已冻结报告不得覆盖，应给 --report 指定新文件名。扩展采用模块入口 `python -m scripts.experiment_cross_domain_stability`。

源码 SHA256：

{table(['文件','SHA256'],list(e['source_hashes'].items()))}

## 9. 下一步研究判据

优先检查相位原点不敏感的多通道周期基函数，与当前样条进行同数据对照；再研究随观测几何缓慢变化的幅度/距离像模型，并通过分块预测与独立几何场景约束，防止漂移项吸收周期。算法必须同时通过真值偏差、结点/表示稳定性和噪声重复性，才适合增加独立精度开关。极轴未知及一般形状需要单独实验，不能从本轮单椭球结果外推。
'''
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(text,encoding='utf-8')
    print(a.report)

if __name__=='__main__':
    main()
