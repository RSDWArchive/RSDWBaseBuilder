// Cooperating asset jobs share a frame budget rather than each spending one.
export function createWorkBudget(milliseconds=5) {
  let start=performance.now(),checks=0,pending=null;
  return function checkpoint(force=false) {
    if(!force&&++checks%64!==0)return null;
    if(!force&&performance.now()-start<milliseconds)return null;
    if(!pending)pending=new Promise(resolve=>requestAnimationFrame(()=>{start=performance.now();pending=null;resolve();}));
    return pending;
  };
}
