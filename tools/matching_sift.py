from pathlib import Path
import cv2,numpy as np,json,time
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'tmp/matching_probe'
sift=cv2.SIFT_create(nfeatures=1600,contrastThreshold=.025)
def read(p):
    a=cv2.imdecode(np.fromfile(p,np.uint8),1)
    scale=min(1,1400/max(a.shape[:2]));a=cv2.resize(a,(round(a.shape[1]*scale),round(a.shape[0]*scale)))
    gray=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY)
    kp,des=sift.detectAndCompute(gray,None)
    return a,kp,des
R=[read(D/f'row_{i}.png') for i in range(2,62)]
A=[read(D/f'ai_{i}.png') for i in range(1,61)]
matcher=cv2.BFMatcher()
def score(q,a):
    qi,qk,qd=q;ai,ak,ad=a
    if qd is None or ad is None or len(qd)<6 or len(ad)<6:return (0,0,0,0,0)
    good=[m for m,n in matcher.knnMatch(qd,ad,k=2) if m.distance<.75*n.distance]
    if len(good)<6:return (0,0,0,0,0)
    src=np.float32([ak[m.trainIdx].pt for m in good]);dst=np.float32([qk[m.queryIdx].pt for m in good])
    # repeated images permit multiple translations; largest consensus wins
    H,mask=cv2.estimateAffine2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=3,maxIters=2000,confidence=.995)
    if H is None:return (0,0,0,0,0)
    mask=mask.ravel().astype(bool);inl=int(mask.sum()); pts=src[mask]
    coverage=float(cv2.contourArea(cv2.convexHull(pts))/(ai.shape[0]*ai.shape[1]))
    if inl<6 or coverage<.005:return (0,0,inl,coverage,0)
    warped=cv2.warpAffine(ai,H,(qi.shape[1],qi.shape[0]))
    region=cv2.warpAffine(np.ones(ai.shape[:2],np.uint8),H,(qi.shape[1],qi.shape[0]),flags=cv2.INTER_NEAREST)
    region=cv2.erode(region,np.ones((5,5),np.uint8)).astype(bool)
    if region.sum()<100:return (0,0,inl,coverage,0)
    qa=cv2.GaussianBlur(qi,(3,3),.6);wa=cv2.GaussianBlur(warped,(3,3),.6)
    diff=np.abs(qa.astype(np.float32)-wa.astype(np.float32))[region]/255
    mae=float(diff.mean());bad=float(np.mean(np.max(diff,axis=1)>.2))
    s=max(0,1-mae*2)*min(1,inl/18)*min(1,coverage/.10)
    return s,mae,inl,coverage,bad
scores=[];t=time.time()
for i,q in enumerate(R):
    vals=[score(q,a) for a in A]; order=sorted(range(60),key=lambda j:vals[j][0],reverse=True)
    print(i+2,[(j+1,tuple(round(v,3) for v in vals[j])) for j in order[:3]],flush=True)
    scores.append({'row':i+2,'top':[(j+1,vals[j]) for j in order[:3]]})
(ROOT/'tmp/matching_sift.json').write_text(json.dumps(scores,indent=2),encoding='utf-8')
print('seconds',time.time()-t)
