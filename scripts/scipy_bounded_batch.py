"""Array adaptation of SciPy 1.13.1's bounded Brent state machine.

Copyright (c) 2001-2002 Enthought, Inc. 2003-2024, SciPy Developers.
BSD-3-Clause; full notice in SCIPY_BSD_LICENSE.txt beside this file.
The sequence, tolerances, parabola acceptance and stopping rules follow
scipy.optimize._optimize._minimize_scalar_bounded; objectives run in batches.
"""
import numpy as np


def bounded_many(objective,lower,upper,xatol=1e-5,maxfun=500):
    a=np.asarray(lower,float).copy();b=np.asarray(upper,float).copy()
    if a.shape!=b.shape or np.any(a>b) or not np.all(np.isfinite([a,b])):
        raise ValueError('有限且等长的有序边界必需')
    golden=.5*(3-np.sqrt(5.));epsilon=np.sqrt(2.2e-16)
    xf=a+golden*(b-a);nfc=xf.copy();fulc=xf.copy()
    fx=objective(xf);fnfc=fx.copy();ffulc=fx.copy()
    rat=np.zeros_like(xf);e=rat.copy();count=np.ones_like(xf,int)
    for _ in range(maxfun):
        middle=.5*(a+b);tol1=epsilon*abs(xf)+xatol/3;tol2=2*tol1
        active=(abs(xf-middle)>(tol2-.5*(b-a)))&(count<maxfun)
        if not np.any(active):break
        attempt=active&(abs(e)>tol1)
        r=(xf-nfc)*(fx-ffulc);q=(xf-fulc)*(fx-fnfc)
        p=(xf-fulc)*q-(xf-nfc)*r;q=2*(q-r)
        p=np.where(q>0,-p,p);q=abs(q);previous_e=e.copy()
        e=np.where(attempt,rat,e)
        accepted=attempt&(abs(p)<abs(.5*q*previous_e))&(p>q*(a-xf))&(p<q*(b-xf))
        step=np.divide(p,q,out=np.zeros_like(p),where=q!=0)
        rat=np.where(accepted,step,rat)
        x=xf+rat
        near=accepted&(((x-a)<tol2)|((b-x)<tol2))
        rat=np.where(near,tol1*(np.sign(middle-xf)+((middle-xf)==0)),rat)
        golden_step=active&~accepted
        e=np.where(golden_step,np.where(xf>=middle,a-xf,b-xf),e)
        rat=np.where(golden_step,golden*e,rat)
        x=xf+(np.sign(rat)+(rat==0))*np.maximum(abs(rat),tol1)
        fu=objective(np.where(active,x,xf));count+=active
        improved=active&(fu<=fx);other=active&~improved
        first=other&((fu<=fnfc)|(nfc==xf))
        second=other&~first&((fu<=ffulc)|(fulc==xf)|(fulc==nfc))
        a=np.where(improved&(x>=xf),xf,np.where(other&(x<xf),x,a))
        b=np.where(improved&(x<xf),xf,np.where(other&(x>=xf),x,b))
        fulc=np.where(improved|first,nfc,np.where(second,x,fulc))
        ffulc=np.where(improved|first,fnfc,np.where(second,fu,ffulc))
        nfc=np.where(improved,xf,np.where(first,x,nfc))
        fnfc=np.where(improved,fx,np.where(first,fu,fnfc))
        xf=np.where(improved,x,xf);fx=np.where(improved,fu,fx)
    success=(count<maxfun)&np.isfinite(xf)&np.isfinite(fx)
    return xf,fx,success,count
