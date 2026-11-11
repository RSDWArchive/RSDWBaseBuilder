// Optional, asynchronous GPU timing. Never wait for the driver on the UI thread.
export function createRenderMetrics(renderer,enabled=false) {
  const gl=renderer.getContext(),ext=enabled?gl.getExtension("EXT_disjoint_timer_query_webgl2"):null;
  const pending=[],gpu={};let active=null,frame=0;
  function poll(){frame++;if(!ext)return;
    if(gl.getParameter(ext.GPU_DISJOINT_EXT)){for(const p of pending)gl.deleteQuery(p.query);pending.length=0;for(const name of Object.keys(gpu))delete gpu[name];return;}
    while(pending.length&&gl.getQueryParameter(pending[0].query,gl.QUERY_RESULT_AVAILABLE)){
      const p=pending.shift();gpu[p.name]=gl.getQueryParameter(p.query,gl.QUERY_RESULT)/1e6;gl.deleteQuery(p.query);
    }
  }
  function begin(name){if(!ext||active||pending.length>8||frame%30)return;const query=gl.createQuery();gl.beginQuery(ext.TIME_ELAPSED_EXT,query);active={query,name};}
  function end(){if(!active)return;gl.endQuery(ext.TIME_ELAPSED_EXT);pending.push(active);active=null;}
  function dispose(){if(active){gl.endQuery(ext.TIME_ELAPSED_EXT);gl.deleteQuery(active.query);active=null;}for(const p of pending)gl.deleteQuery(p.query);pending.length=0;}
  return {poll,begin,end,dispose,stats:()=>({gpu_timer_available:!!ext,gpu_ms:{...gpu}})};
}
