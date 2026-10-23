# -*- coding: utf-8 -*-
"""Report the layered experiment, including metadata-only provenance correction."""
from pathlib import Path
from urllib.parse import quote
import sys
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_optional_period_precision import sha256

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
        ['| '+' | '.join(map(str,row))+' |' for row in rows])

METHODS=[('H1','centroid'),('fourier_H1','profile_shape'),('fourier','centroid'),('fourier','profile_shape'),
    ('spline','centroid'),('spline','profile_shape'),('kernel_all','centroid'),('kernel_all','profile_shape')]
LABELS={'H1':'基础 H=1','fourier_H1':'共频 H=1','fourier':'留出选参 Fourier','spline':'留出选参样条','kernel_all':'全配对核'}
REPS={'centroid':'质心','profile_shape':'归一化距离像'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--repaired-controls',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if args.report.exists():
        raise FileExistsError('Do not overwrite frozen reports')
    d=json.loads(args.results.read_text(encoding='utf-8'))
    rows=d['records']
    # The fitting run used an earlier metadata revision. Verify identity rather
    # than pretending this report re-executed estimation on the corrected files.
    mappings=[]
    newmanifest=json.loads((args.repaired_controls/'generation.json').read_text(encoding='utf-8'))
    original_echo=[Path(k) for k in d['input_hashes'] if k.endswith('echo.npz') and 'metadata_reviewed' in k]
    if len(original_echo)!=2:
        raise ValueError('Expected the two explicitly recorded original control inputs')
    for old in original_echo:
        new=args.repaired_controls/old.parent.name/'echo.npz'
        if sha256(old)!=d['input_hashes'][str(old)]:
            raise ValueError('Actual fitted artifact changed')
        with np.load(old) as a,np.load(new) as b:
            if a.files!=b.files:
                raise ValueError('Metadata revision changed fields')
            for name in a.files:
                if name!='metadata_json' and not np.array_equal(a[name],b[name]):
                    raise ValueError('Corrected artifact changed numerical data')
            am=json.loads(str(a['metadata_json'].item()))
            bm=json.loads(str(b['metadata_json'].item()))
            ignored={'observation_info_path','original_observation_info_path'}
            if {k:v for k,v in am.items() if k not in ignored}!={k:v for k,v in bm.items() if k not in ignored}:
                raise ValueError('Correction changed algorithm-consumed metadata')
            if sha256(bm['observation_info_path'])!=bm['observation_info_sha256']:
                raise ValueError('Corrected observation path/hash inconsistent')
        mappings.append([old.parent.name,sha256(old),sha256(new)])
    def lookup(geometry,method,representation,mode):
        return next(r for r in rows if r['stage']=='comparison' and r['geometry']==geometry and r['method']==method
            and r['representation']==representation and r['compensation']==mode)
    clean=[]
    azimuth=[]
    dynamic=[]
    for method,name in METHODS:
        label=f'{LABELS[method]} / {REPS[name]}'
        r=lookup('stationary',method,name,'off')
        clean.append([label,f"{r['period_s']:.6f}",f"{r['error_s']:+.6f}"])
        for geometry,collection in [('azimuth_only',azimuth),('original_dynamic',dynamic)]:
            collection.append([label]+[f"{lookup(geometry,method,name,mode)['error_s']:+.6f}" for mode in ('off','linear','per_epoch')])
    noise=[]
    for method,name in METHODS:
        if method=='fourier_H1':
            continue
        errors=np.array([r['error_s'] for r in rows if r['stage']=='noise' and r['method']==method and r['representation']==name])
        if len(errors)!=3:
            raise ValueError('Three paired noise seeds required')
        noise.append([f'{LABELS[method]} / {REPS[name]}',f'{errors.mean():+.6f}',f'{errors.std(ddof=1):.6f}',f'{np.sqrt(np.mean(errors**2)):.6f}'])
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),constrained_layout=True)
    labels=['基础 H1','Fourier','周期样条','全配对核']
    methods=['H1','fourier','spline','kernel_all']
    errors=[lookup('stationary',m,'centroid','off')['error_s'] for m in methods]
    axes[0].bar(labels,errors,color=['#4776b4','#6aa68d','#dc995b','#9180ab'])
    axes[0].axhline(0,color='gray',lw=1)
    axes[0].set_ylabel('半周期偏差 / s')
    axes[0].set_title('固定视线：质心路线，无噪声')
    for geometry,label in [('stationary','固定几何'),('azimuth_only','仅方位变化'),('original_dynamic','原动态几何')]:
        rr=[lookup(geometry,'H1','centroid',mode)['error_s'] for mode in ('off','linear','per_epoch')]
        axes[1].plot(['不补偿','线性速率','逐时刻经度'],rr,'o-',label=label)
    axes[1].set_title('冻结基础算法：比较几何补偿')
    axes[1].set_ylabel('半周期偏差 / s')
    axes[1].grid(alpha=.2)
    axes[1].legend()
    imagedir=args.report.parent/f'{args.report.stem}_figures'
    imagedir.mkdir(parents=True,exist_ok=True)
    for suffix in ('png','svg'):
        fig.savefig(imagedir/f'2026-10-11_COMPARISON.{suffix}',dpi=180)
    plt.close(fig)
    selected_table=[]
    for key,cfg in d['selected'].items():
        rec=next(r for r in rows if r['stage']=='selected' and f"{r['method']}:{r['representation']}"==key)
        selected_table.append([key,json.dumps(cfg),f"{rec['cv_mse']:.6f}"])
    text=f'''# 固定视线与变化视线的分层周期实验（2026-10-11）

按“先固定视线比较估计器，再加入视线变化比较补偿”的顺序完成了第一组分层实验。固定几何中，基础质心 H=1 的半周期偏差为 +0.063279 s；仅引入视线方位变化后，不补偿偏差为 +3.267710 s，逐时刻补偿后为 +0.370586 s。原动态观测则为 +4.493480 / +1.596767 s。这些结果说明，当前秒级偏差不能解释成普遍的周期测量物理极限；本次已验证路线中，更复杂的模型也没有一致优于基础算法。

## 1. 哪些路线已经验证

| 路线 | 实际验证状态 | 范围 |
| --- | --- | --- |
| 现有质心 H=1 与多谐波 | 已验证 | 原动态数据及本轮固定/方位单因素数据 |
| 多通道共频 Fourier、惩罚变量投影 | 本轮已实现和验证 | 从数据学习系数，无形状/初始相位输入；不是换名字后的标量 H=1 |
| 周期三次样条 | 已验证 | 上一轮及本轮分层、留出、噪声比较 |
| 距离像核相似性（CKP 思想迁移） | 已验证 | 本轮全部配对；不是原论文完整复现 |
| 独立 PDM、条件熵、GP | 尚未实验 | 周期样条不等于完整 PDM，CKP 不等于条件熵 |
| 非均匀 Optimized DMD、矩阵铅笔、原子范数 | 尚未实验 | 仍需核查采样、谱稀疏与模态选择条件 |
| SimPer/CycleCL 等深度表征 | 尚未训练验证 | 需要多个独立形状、周期及几何场景，当前单场景不能作泛化训练集 |
| 微多普勒轨迹、APT/ISAR、多站散斑 | 尚未完成项目精度验证 | 当前冻结数据每 Run 只有一个脉冲，不能拼接相位重置的 Run 假装形成长期相干 CPI |

因此不能把文献中的全部技术路线说成已经验证，以下排名只在本轮明确实现的估计器、表示和扫描范围内成立。

## 2. 三层数据与受控变量

共同使用 2000 个原始散射时刻，跨度约 33735.378 s，椭球真实自转周期 10800 s，评价重复半周期 5400 s；Chirp 带宽 150 MHz、脉宽 50 μs、采样率 200 MHz，1280 个面元、float32 回波生成。固定组和方位组都重新计算完整 IQ，视线用于面元照射、接收及差分传播路径，未对原 IQ 仅修改视线标签。真值形状只在模拟器生成数据时使用，不传入估计器；真值周期只用于模拟与事后评价。

| 数据组 | 固定的因素 | 改变的因素 |
| --- | --- | --- |
| stationary | 收发视线、距离、距离速度、收发光行时、名义 ADC 相对偏移 | 目标自转、原始不规则散射时刻 |
| azimuth_only | 视线倾角、收发夹角、距离、速度及名义 ADC 相对偏移 | 收发视线共同绕极轴改变方位，经度跨度 0.559260° |
| original_dynamic | 原冻结观测安排、信号和形体配置 | 原视线、倾角、距离、速度与采样变化全部保留 |

前两组是合成受控几何，不是新的真实天文观测计划。固定距离时，以散射时刻减去发射光行时得到发射时刻、加接收光行时得到接收时刻；生产者仍用每 Run 唯一全局 ADC 索引求和，保存二维脉冲行，再由反演读取完整脉压相关。本输入的单脉冲 Run 相互分离，不存在共享 ADC 行的重复计权。

静态 ADC 的名义相对偏移固定，但绝对时刻相减仍受 float64 epoch 量化影响；测试要求其变动不超过两倍 epoch 浮点间距，而不声称对任意时刻字节恒定。实际冻结控制组的偏移跨度为零。所有 20,806,000 个保存样点均有效。

方位单因素组才能隔离经度相位变化。原动态组与固定组还存在其他差异，不能把两组之间的全部误差差异归因于视线；倾角、收发夹角或采样影响需要进一步单因素实验。

## 3. 参数选择及算法约定

基础质心 H=1 全范围盲搜 1800–14400 s，各新方法在它给出的 ±2% 范围连续细化，参考值不用于设定搜索范围或选参。新方法尚未完成全局消歧，比较属于候选条件下的局部精度。

固定组用五个连续时间块留出，每折重拟合周期及系数，归一尺度仅来自训练集。Fourier 扫描 H=1/2/4/8/16、惩罚 0/0.001/0.1，成对正弦/余弦使用相同缩减权重，因此常数相位平移不影响 Fourier 目标；样条扫描 K=8/16/32/64、惩罚 0.001/0.1/10。留出误差用于同一表示内部选复杂度，不按真值挑配置，也不跨表示按 MSE 大小挑表示。候选中心来自全数据基础算法，因此留出不是全流程独立外推验证。

{table(['模型与表示','固定组选定参数','留出 MSE'],selected_table)}

四个选择都命中 H16/K64 的复杂度上边界。应扩大扫描或研究其他表示后再讨论模型收敛；不能声称本轮已经找到这些技术路线的最高可达精度。变化组和噪声组复用上述参数，不重新按其真值或留出调参。

全配对核使用 1,999,000 个观测对。固定的是相位核宽度 0.5 和幅度宽度倍率 1；绝对幅度核宽度由每组数据的全配对距离中位数计算，会随几何或噪声重标定。配对不是独立观测，不能将观测对数量当作有效样本数。

归一化距离像使用完整原生相关功率、64 个中央箱和两侧尾箱，再除以整行总功率，功率积分守恒。采集路径窗元数据用于分箱，不使用形状给定的门限或相位模板。

## 4. 固定视线：先比较估计器

所有方法不做视线补偿，单位为秒。共同相位 H=1 的质心结果与生产基础算法一致，另列距离像 H=1 作为同阶多通道对照。

{table(['算法 / 表示','估计半周期/s','有符号偏差/s'],clean)}

本次无噪声、固定几何、所列选参范围内，基础质心 H=1 的绝对偏差最小，约 63 ms。增加周期函数复杂度或距离像维度没有自动改善周期准确度；更低的留出预测误差也不等于更小的周期真值误差。63 ms 是该场景的一次实验偏差，不是任何目标都能达到的系统精度，不是当前算法的物理或数值下限。

## 5. 仅方位变化：冻结算法后比较补偿

线性补偿以观测几何经度拟合恒定角速度；逐时刻补偿使用每个散射时刻的有效收发视线经度，半周期相位偏移为经度变化的负两倍。两种方案都显式使用已知极轴 RA=105°、Dec=−66°；没有输入初始自转相位或形状。

{table(['算法 / 表示','不补偿偏差/s','线性速率补偿偏差/s','逐时刻补偿偏差/s'],azimuth)}

对基础质心 H=1，逐时刻补偿将偏差从 +3.267710 s 降至 +0.370586 s，比线性速率的 +0.385937 s 略好。它没有回到固定组 +0.063279 s，因此不能把补偿后的剩余偏差都解释成经度算法出错：方位变化改变有效相位采样位置，有限周期函数近似的偏差也可能变化。不同估计器的反应说明应联合检查波形模型与补偿，而不是按真值给每组独立调参。

## 6. 原动态几何：复杂场景中的迁移

{table(['算法 / 表示','不补偿偏差/s','线性速率补偿偏差/s','逐时刻补偿偏差/s'],dynamic)}

基础质心 H=1 的逐时刻方案为 +1.596767 s，比线性速率 +1.610347 s 略小，主要改善仍来自加入经度补偿本身。Fourier 距离像配置出现约 +0.178340 s 的单次偏差，但它在固定组及方位组分别为约 +1.49/+1.41 s；不能凭这个动态组结果认定它稳定达到亚秒精度，也没有对动态组做本轮噪声重复。不同误差来源的相互抵消是一种可能解释，需要独立几何场景检验。

![分层算法与几何补偿对照](<{quote(imagedir.name)}/2026-10-11_COMPARISON.png>)

## 7. 固定组配对噪声重复

在完整原始 IQ 全体样点平均功率定义下加入 20 dB 复白噪声，种子 20261031/20261032/20261033。每种算法使用同一份噪声 IQ，重新脉压、提取特征及盲搜候选，参数保持固定组无噪声留出选择。三个种子只作探索，不给出可靠置信区间。

{table(['算法 / 表示','平均偏差/s','样本标准差/s','RMSE/s'],noise)}

无噪声偏差、含噪 RMSE 和重复波动必须分别看；不能将最小的单次偏差直接作为加噪后的算法排名，也不能用稳定性代替准确度。本轮噪声只检验固定组，没有覆盖动态几何的噪声、时钟、轨道或极轴误差。

## 8. 验证与元数据修正

两组回波生成耗时 {d['generation']['seconds']:.3f} s，设备 {d['generation']['device']}；拟合完成 {len(rows)} 条结果，耗时 {d['seconds']:.3f} s，记录时间 `{d['created_utc']}`。耗时只作为本次会话参考，不作性能优劣比较。新增 7 项测试与相关研究/可选方法测试共 39 项通过，覆盖独立旋转几何、三事件关系、ADC 浮点上界、H 阶扰动、Fourier 增广最小二乘成本、常数相位不变性、训练尺度与非线性经度补偿分支。

生成器原样保留了部分顶层真实观测来源标签，审查后另存修正版，把 frame/time_scale/solver_version 明确改为合成控制来源。首次修正版曾保留旧 observation 路径，已再另存最终修正版，保留 original 路径并使当前路径与 SHA256 对应。未覆盖原始产物或改变 IQ、任何数值数组及估计器使用的信号元数据。实际拟合使用的是首次元数据修正版；本报告逐字段验证其与最终版本除路径历史字段外完全一致，没有声称在最终版本重新运行估计。

{table(['控制组','实际拟合 Echo SHA256','最终元数据修正版 Echo SHA256'],mappings)}

实际拟合输入哈希及全部源码哈希存于 JSON。生成器和估计器在启动时冻结依赖，在保存时拒绝输入或源码变化。元数据修正版另记录生成来源、原产物哈希、修正器源码哈希及数值不变校验；原输出完整保留。以上前提由冻结 singleton-run 数据和脚本断言保证，不外推到共享 ADC、多脉冲 Run 或任意观测计划。

## 9. 重建命令与下一步

在仓库根目录运行，各输出目录及报告路径必须不存在：

```powershell
conda activate pytorch
python scripts/generate_layered_period_controls.py --output tmp/layered_period_controls_new
python scripts/repair_layered_control_metadata.py --controls tmp/layered_period_controls_new --output tmp/layered_period_controls_new_metadata_reviewed
python scripts/experiment_layered_period.py --controls tmp/layered_period_controls_new_metadata_reviewed --output tmp/layered_period_fit_new
python -m pytest tests/test_layered_period_experiment.py tests/test_research_period_estimators.py tests/test_optional_period_methods.py -q
python scripts/check_doc_math.py
```

本次报告及图由 `scripts/summarize_layered_period.py --results tmp/layered_period_fit_20261011/results.json --repaired-controls tmp/layered_period_controls_20261011_provenance_final --report <新文件名>` 生成；该历史证据汇总入口显式核验本次元数据版本映射。新实验应按自身输入路径整理新报告，不覆盖已冻结证据。

后续沿这套分层基准扩大复杂度扫描，再补 PDM/条件熵与非均匀 DMD 等适用路线；用独立周期、初始相位、采样安排和视角检验“谁更准”是否能稳定成立。补偿研究还需将倾角、双站夹角、距离运动及采样变化分别加入，之后再讨论未知极轴。继续保持基础功能与附加算法独立，不将单次接近真值的配置直接加入 GUI 精度选项。

源码 SHA256：

{table(['源码文件','SHA256'],list(d['source_hashes'].items()))}
'''
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(text,encoding='utf-8')
    print(args.report)

if __name__=='__main__':
    main()
