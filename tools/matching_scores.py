from pathlib import Path
import cv2,numpy as np,json,time
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'tmp/matching_probe'
def read(p):return cv2.imdecode(np.fromfile(p,np.uint8),1)
def norm(arr,h=96):return cv2.resize(arr,(max(2,round(arr.shape[1]*h/arr.shape[0])),h),interpolation=cv2.INTER_AREA)
R=[norm(read(D/f'row_{i}.png')) for i in range(2,62)]
A=[norm(read(D/f'ai_{i}.png')) for i in range(1,61)]
def score(q,a):
    big=np.tile(a,(1, max(2,(q.shape[1]+a.shape[1]-1)//a.shape[1]+1),1))
    result=cv2.matchTemplate(big,q,cv2.TM_SQDIFF)
    _,_,loc,_=cv2.minMaxLoc(result)
    x=loc[0]; crop=big[:,x:x+q.shape[1]]
    diff=np.abs(q.astype(np.float32)-crop)/255
    mse=float(np.mean(diff**2));mae=float(diff.mean())
    # fraction of significantly different pixels helps reveal localized edits
    bad=float(np.mean(np.max(diff,axis=2)>.14))
    return 1-mse**.5,mae,bad
scores=[]
t=time.time()
for i,q in enumerate(R):
    vals=[score(q,a) for a in A]; order=sorted(range(60),key=lambda j:vals[j][0],reverse=True)
    print(i+2,[(j+1,tuple(round(v,3) for v in vals[j])) for j in order[:3]],flush=True)
    scores.append({'row':i+2,'top':[(j+1,vals[j]) for j in order[:3]]})
(ROOT/'tmp/matching_scores.json').write_text(json.dumps(scores,indent=2),encoding='utf-8')
print('seconds',time.time()-t)
