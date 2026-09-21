#!/usr/bin/env python3
"""用候选示例验证 v4 完整分流；未评级项进入复核队列，结果不代表真实周报质量。"""
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPTS=ROOT/"scripts"
def run(*args):
    r=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,text=True,capture_output=True)
    if r.returncode: raise RuntimeError(r.stderr)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--demo",default=str(ROOT/"examples/demo-merged-candidates.json")); ap.add_argument("--workdir",required=True); ap.add_argument("--out",required=True); a=ap.parse_args()
    wd=Path(a.workdir); wd.mkdir(parents=True,exist_ok=True)
    cl,rk,th,final=wd/"clusters.json",wd/"ranked.json",wd/"theses.json",wd/"final_weekly_report.json"
    run(SCRIPTS/"cluster_events.py",a.demo,"-o",cl); run(SCRIPTS/"rank_events.py",cl,a.demo,"-o",rk); run(SCRIPTS/"build_theses.py",rk,"-o",th)
    run(SCRIPTS/"editorial_pass.py","prepare",rk,"--theses",th,"--week-start","2026-09-07","--week-end","2026-09-13","--json-out",final)
    d=json.loads(final.read_text()); levels={k:0 for k in ["S","A","B","noise","unrated"]}
    for layer in ["core_events","watchlist","editorial_candidate_pool","human_review_queue","appendix_events","excluded_events"]:
        for e in d[layer]: levels[e["signal_level"]]+=1
    result={"input_event_count":len(d["input_event_ids"]),"retained_event_count":sum(len(d[x]) for x in ["core_events","watchlist","editorial_candidate_pool","human_review_queue","appendix_events","excluded_events"]),"signal_levels":levels,"note":"demo 只验证完整分流；未完成 Agent 定稿，因此不渲染发布文件。"}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n"); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
