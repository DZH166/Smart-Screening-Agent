from pathlib import Path
import cv2,numpy as np,time,json
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'tmp/matching_probe'
def read(p):return cv2.imdecode(np.fromfile(p,np.uint8),1)
def norm(a,h):return cv2.resize(a,(max(2,round(a.shape[1]*h/a.shape[0])),h),interpolation=cv2.INTER_AREA)
R=[norm(read(D/f'row_{i}.png'),64) for i in range(2,62)]
A=[read(D/f'ai_{i}.png') for i in range(1,61)]
def hist(a):
    lab=cv2.cvtColor(a,cv2.COLOR_BGR2LAB)
    h=cv2.calcHist([lab],[0,1,2],None,[12,16,16],[0,256]*3);return cv2.normalize(h,h,norm_type=cv2.NORM_L1)
RH=[hist(a) for a in R]; AH=[hist(a) for a in A]
def match(q,a):
    best=(0,0,0)
    # allow modest crop; no rotation, color modifications or arbitrary new scales
    for h in range(58,96,2):
        tile=norm(a,h);big=np.tile(tile,(2,max(2,(q.shape[1]+tile.shape[1]-1)//tile.shape[1]+1),1))
        mm=cv2.matchTemplate(big,q,cv2.TM_SQDIFF)
        mn,_,loc,_=cv2.minMaxLoc(mm); x,y=loc
        diff=np.abs(q.astype(np.float32)-big[y:y+q.shape[0],x:x+q.shape[1]])/255
        s=1-float(np.mean(diff**2))**.5
        if s>best[0]:best=(s,h,float(np.mean(np.max(diff,axis=2)>.2)))
    return best
t=time.time()
for i,q in enumerate(R):
    hs=[cv2.compareHist(RH[i],h,cv2.HISTCMP_BHATTACHARYYA) for h in AH]
    ids=sorted(range(60),key=lambda j:hs[j])[:5]
    if i+2 not in [17,18,19,20,21,22,23,24,25,41,47,49,50,51,52,53,54,55,56,57]:continue
    vals=sorted([(j+1,match(q,A[j]),round(hs[j],3)) for j in ids],key=lambda x:x[1][0],reverse=True)
    print(i+2,vals[:3],flush=True)
print(time.time()-t)
