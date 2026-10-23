"""Batched bounded Brent proposals; final winner uses reference SVD/Brent.

Research-only, fixed H1 complete-mask design. Every grid maximum and endpoint
gets a proposal. Numerical close competition uses the original full selector.
"""
import numpy as np
from scipy import optimize,signal
from scripts.monte_carlo_period import FixedPredictiveSearch
from scripts.scipy_bounded_batch import bounded_many


class BatchedPredictiveSearch(FixedPredictiveSearch):
    def __init__(self,*args,device='cpu',**kwargs):
        super().__init__(*args,**kwargs)
        self.device='cpu'
        self.normal_equation_condition_bound=None
        if device=='cuda:0':
            import torch
            if torch.cuda.is_available():
                phase=self._phases(self.grid)
                design=np.stack((np.ones_like(phase),np.cos(phase),np.sin(phase)),axis=2)
                maximum_step=float(np.max(abs(np.diff(1/self.grid))))
                bounds=[]
                for train,_,*_ in self.blocks:
                    gram=np.einsum('gni,gnj,n->gij',design[:,train],design[:,train],self.w[train])
                    eigen=np.linalg.eigvalsh(gram)
                    perturbation=2*np.pi*maximum_step*np.sqrt(np.sum(self.w[train]*self.t[train]**2))
                    lower=float(np.sqrt(eigen[:,0].min())-perturbation)
                    upper=float(np.sqrt(eigen[:,-1].max())+perturbation)
                    bounds.append(upper/lower if lower>0 else np.inf)
                self.normal_equation_condition_bound=max(bounds)
                # Weyl's bound plus a sin/cos Lipschitz bound covers every
                # point between grid samples, including all refinement boxes.
                if self.normal_equation_condition_bound<1e3:
                    self.device='cuda:0';self.torch=torch
                    self.gpu_t=torch.as_tensor(self.t,device=self.device)
                    self.gpu_phase=None if self.phase_offset is None else torch.as_tensor(self.phase_offset,device=self.device)
                    self.gpu_fold=torch.as_tensor(np.array([np.where(self.labels==k,self.w,0.) for k in range(5)]),device=self.device)
                    self.gpu_z=None

    def objective_many(self,periods,z,denominator):
        if self.device=='cpu':return self._objective_cpu(periods,z,denominator)
        torch=self.torch
        with torch.inference_mode():
            if self.gpu_z is not z:
                self.gpu_z=z
                self.gpu_y=torch.as_tensor(z,device=self.device)
                self.gpu_denominator=torch.as_tensor(denominator,device=self.device)
                self.gpu_response=(self.gpu_fold[:,:,None]*self.gpu_y[None,:,:]).permute(1,0,2).reshape(len(self.t),-1)
                self.gpu_yy=self.gpu_fold@(self.gpu_y*self.gpu_y)
            p=torch.as_tensor(periods,device=self.device)
            phase=2*np.pi*self.gpu_t[None,:]/p[:,None]
            if self.gpu_phase is not None:phase=phase+self.gpu_phase[None,:]
            design=torch.stack((torch.ones_like(phase),torch.cos(phase),torch.sin(phase)),dim=2)
            g,n,_=design.shape;c=z.shape[1]
            products=(design[:,:,:,None]*design[:,:,None,:]).reshape(g,n,9)
            test_gram=(products.transpose(1,2).reshape(g*9,n)@self.gpu_fold.T).reshape(g,3,3,5).permute(3,0,1,2)
            test_rhs=(design.transpose(1,2).reshape(g*3,n)@self.gpu_response).reshape(g,3,5,c).permute(2,0,1,3)
            gram=test_gram.sum(0)[None,:,:,:]-test_gram
            rhs=test_rhs.sum(0)[None,:,:,:]-test_rhs
            solved=torch.linalg.solve_ex(gram,rhs,check_errors=False)
            if torch.any(solved.info):return self._objective_cpu(periods,z,denominator)
            beta=solved.result
            numerator=(self.gpu_yy[:,None,:]-2*(beta*test_rhs).sum(2)+
                torch.einsum('kgic,kgij,kgjc->kgc',beta,test_gram,beta)).sum(0)
            # torch.median uses the lower median for even channel counts;
            # this accelerator's complete-mask experiment always has five.
            if c%2==0:return self._objective_cpu(periods,z,denominator)
            return torch.median(1-numerator/self.gpu_denominator,dim=1).values.cpu().numpy()

    def _objective_cpu(self,periods,z,denominator):
        periods=np.asarray(periods)
        phase=self._phases(periods)
        design=np.stack((np.ones_like(phase),np.cos(phase),np.sin(phase)),axis=2)
        fold_weights=np.array([np.where(self.labels==k,self.w,0.) for k in range(5)])
        g,n,_=design.shape;c=z.shape[1]
        products=(design[:,:,:,None]*design[:,:,None,:]).reshape(g,n,9)
        test_gram=(products.transpose(0,2,1).reshape(g*9,n)@fold_weights.T).reshape(g,3,3,5).transpose(3,0,1,2)
        response=(fold_weights[:,:,None]*z[None,:,:]).transpose(1,0,2).reshape(n,5*c)
        test_rhs=(design.transpose(0,2,1).reshape(g*3,n)@response).reshape(g,3,5,c).transpose(2,0,1,3)
        gram=test_gram.sum(0)[None,:,:,:]-test_gram
        rhs=test_rhs.sum(0)[None,:,:,:]-test_rhs
        eigen=np.linalg.eigvalsh(gram)
        safe=eigen[:,:,0]>eigen[:,:,-1]*1e-6
        beta=np.empty_like(rhs)
        beta[safe]=np.linalg.solve(gram[safe],rhs[safe])
        for k,j in np.argwhere(~safe):
            train=self.labels!=k;root=np.sqrt(self.w[train])
            beta[k,j]=np.linalg.lstsq(design[j,train]*root[:,None],z[train]*root[:,None],rcond=None)[0]
        yy=fold_weights@(z*z)
        numerator=(yy[:,None,:]-2*np.sum(beta*test_rhs,axis=2)+
            np.einsum('kgic,kgij,kgjc->kgc',beta,test_gram,beta)).sum(0)
        return np.median(1-numerator/denominator,axis=1)

    def select(self,values,return_grid=False):
        z=self.normalize(values)
        skill=self.score_grid(z);scores=np.median(skill,axis=1)
        denominator=np.zeros(z.shape[1])
        for train,test,*_ in self.blocks:
            mean=np.average(z[train],weights=self.w[train],axis=0)
            denominator+=np.sum(self.w[test,None]*(z[test]-mean)**2,axis=0)
        peaks=np.unique(np.r_[signal.find_peaks(scores)[0],0,len(scores)-1])
        lower=self.grid[np.maximum(0,peaks-1)].copy()
        upper=self.grid[np.minimum(len(self.grid)-1,peaks+1)].copy()
        original_lower,original_upper=lower.copy(),upper.copy()
        proposed,negative_quality,success,evaluations=bounded_many(
            lambda p:-self.objective_many(p,z,denominator),lower,upper)
        quality=np.where(success,-negative_quality,-np.inf)
        quality_original=scores[peaks]
        periods=np.where(quality>quality_original,proposed,self.grid[peaks])
        quality=np.maximum(quality,quality_original)
        order=np.lexsort((periods,-quality))
        if len(order)>1 and quality[order[0]]-quality[order[1]]<1e-8:
            return super().select(values,return_grid=return_grid)
        # Use precisely the production scalar SVD and SciPy bounded method for
        # the winning bracket, after evaluating all other maxima as well.
        winner=order[0]
        fit=optimize.minimize_scalar(lambda p:-float(np.median(self.scalar(p,z))),
            bounds=(original_lower[winner],original_upper[winner]),method='bounded')
        period=float(self.grid[peaks[winner]]);score=float(quality_original[winner])
        if fit.success and -fit.fun>score:period,score=float(fit.x),float(-fit.fun)
        periods[winner]=period;quality[winner]=score
        order=np.lexsort((periods,-quality))
        if order[0]!=winner:return super().select(values,return_grid=return_grid)
        result=dict(period_s=period,score=score,
            candidates=[dict(period_s=float(periods[i]),score=float(quality[i])) for i in order[:10]],
            local_maxima_and_endpoints=len(peaks),proposal_maximum_evaluations=int(np.max(evaluations)),
            refinement_device=self.device,normal_equation_condition_bound=self.normal_equation_condition_bound)
        if return_grid:result.update(channel_grid=skill,grid_scores=scores)
        return result
