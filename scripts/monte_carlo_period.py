"""Fixed-design H1 full-mask predictive scoring for the receiver experiment.

Only a research accelerator: unsupported inputs are explicitly rejected.
SVD projectors depend solely on the validated fixed time/weight/fold design.
"""
import numpy as np
from scipy import signal,optimize
from inversion.src.joint_period import select_predictive_period


class FixedPredictiveSearch:
    def __init__(self,times,runs,weights,minimum=1800.,maximum=14400.,grid=4000,phase_offset=None):
        self.t=np.asarray(times,float)-np.min(times)
        self.phase_offset=None if phase_offset is None else np.asarray(phase_offset,float)
        if self.phase_offset is not None and (self.phase_offset.shape!=self.t.shape or not np.all(np.isfinite(self.phase_offset))):
            raise ValueError('phase_offset must be finite and match the fixed time design')
        self.runs=np.asarray(runs)
        self.w=np.asarray(weights,float)/np.max(weights)
        if not np.all(np.isfinite(self.t)) or not np.all(self.w>0):raise ValueError('固定设计要求完整正权时标')
        ordered=sorted(np.unique(runs).tolist(),key=lambda r:float(np.median(self.t[self.runs==r])))
        if len(ordered)<10:raise ValueError('固定设计要求至少10个有效Run')
        assignment={r:i%5 for i,r in enumerate(ordered)}
        self.labels=np.array([assignment[r] for r in self.runs])
        self.grid=np.sort(1/np.linspace(1/maximum,1/minimum,grid))
        self.minimum,self.maximum=minimum,maximum
        phase=self._phases(self.grid)
        design=np.stack((np.ones_like(phase),np.cos(phase),np.sin(phase)),axis=2)
        self.blocks=[]
        for k in range(5):
            train=self.labels!=k;test=~train
            root=np.sqrt(self.w[train])
            matrix=design[:,train]*root[None,:,None]
            singular=np.linalg.svd(matrix,compute_uv=False)
            if np.any(singular[:,-1]<singular[:,0]*1e-10):raise ValueError('固定设计含病态网格')
            projection=np.linalg.pinv(matrix)*root[None,None,:]
            tx=design[:,test]
            cross=tx.transpose(0,2,1)*self.w[test][None,None,:]
            gram=np.einsum('gni,gnj,n->gij',tx,tx,self.w[test])
            self.blocks.append((train,test,projection.reshape(-1,train.sum()),cross.reshape(-1,test.sum()),gram))

    def _phases(self,periods):
        phase=2*np.pi*self.t[None,:]/np.asarray(periods)[:,None]
        return phase if self.phase_offset is None else phase+self.phase_offset[None,:]

    def normalize(self,values):
        y=np.asarray(values,float)
        if y.ndim!=2 or y.shape[0]!=len(self.t) or not np.all(np.isfinite(y)):
            raise ValueError('固定设计加速仅覆盖完整有限通道')
        scale=np.max(abs(y),axis=0)
        if np.any(scale==0):raise ValueError('退化通道需生产排除')
        z=y/scale
        z-=np.average(z,weights=self.w,axis=0)
        variance=np.average(z*z,weights=self.w,axis=0)
        if np.any(variance<=0):raise ValueError('常量通道需生产排除')
        z/=np.sqrt(variance)
        trend=np.column_stack((np.ones(len(self.t)),self.t/np.ptp(self.t)))
        root=np.sqrt(self.w)
        fitted=trend@np.linalg.lstsq(trend*root[:,None],z*root[:,None],rcond=None)[0]
        if np.any(np.linalg.norm((z-fitted)*root[:,None],axis=0)<=1e-12*np.linalg.norm(z*root[:,None],axis=0)):
            raise ValueError('纯趋势需生产排除')
        for j in range(z.shape[1]):
            for k in range(j):
                if min(np.max(abs(z[:,j]-z[:,k])),np.max(abs(z[:,j]+z[:,k])))<=1e-10:
                    raise ValueError('复制通道需生产去重')
        return z

    def score_grid(self,z):
        numerator=np.zeros((len(self.grid),z.shape[1]));denominator=np.zeros(z.shape[1])
        for train,test,projection,cross,gram in self.blocks:
            beta=(projection@z[train]).reshape(len(self.grid),3,-1)
            xy=(cross@z[test]).reshape(len(self.grid),3,-1)
            yy=np.sum(self.w[test,None]*z[test]**2,axis=0)
            numerator+=yy-2*np.sum(beta*xy,axis=1)+np.einsum('gic,gij,gjc->gc',beta,gram,beta)
            mean=np.average(z[train],weights=self.w[train],axis=0)
            denominator+=np.sum(self.w[test,None]*(z[test]-mean)**2,axis=0)
        return 1-numerator/denominator

    def scalar(self,period,z):
        phase=2*np.pi*self.t/period
        if self.phase_offset is not None:phase=phase+self.phase_offset
        x=np.column_stack((np.ones(len(self.t)),np.cos(phase),np.sin(phase)))
        numerator=np.zeros(z.shape[1]);denominator=np.zeros(z.shape[1])
        for train,test,*_ in self.blocks:
            root=np.sqrt(self.w[train])
            beta=np.linalg.lstsq(x[train]*root[:,None],z[train]*root[:,None],rcond=None)[0]
            numerator+=np.sum(self.w[test,None]*(z[test]-x[test]@beta)**2,axis=0)
            mean=np.average(z[train],weights=self.w[train],axis=0)
            denominator+=np.sum(self.w[test,None]*(z[test]-mean)**2,axis=0)
        return 1-numerator/denominator

    def select(self,values,return_grid=False):
        z=self.normalize(values)
        skill=self.score_grid(z)
        scores=np.median(skill,axis=1)
        peaks=np.unique(np.r_[signal.find_peaks(scores)[0],0,len(scores)-1])
        candidates=[]
        for index in peaks:
            period=float(self.grid[index]);score=float(scores[index])
            lower,upper=self.grid[max(0,index-1)],self.grid[min(len(scores)-1,index+1)]
            if lower<upper:
                fit=optimize.minimize_scalar(lambda p:-float(np.median(self.scalar(p,z))),bounds=(lower,upper),method='bounded')
                if fit.success and -fit.fun>score:period,score=float(fit.x),float(-fit.fun)
            candidates.append(dict(period_s=period,score=score))
        candidates.sort(key=lambda r:(-r['score'],r['period_s']))
        result=dict(period_s=candidates[0]['period_s'],score=candidates[0]['score'],candidates=candidates[:10])
        if return_grid:result.update(channel_grid=skill,grid_scores=scores)
        return result

    def production(self,values):
        features={f'channel{i}':values[:,i] for i in range(values.shape[1])}
        return select_predictive_period(self.t,features,self.runs,
            {name:{'grid_periods_s':self.grid} for name in features},weights=self.w,
            min_period=self.minimum,max_period=self.maximum,phase_offset=self.phase_offset)
