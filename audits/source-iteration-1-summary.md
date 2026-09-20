# 来源 Endpoint 第一轮迭代摘要

- 审计对象：15个基础来源 + 29个微信C1，共44个来源、65条endpoint记录。
- 入口配置：42个来源已配置，联网探测时36个来源至少一个入口可达。
- 微信C1：27/29已有候选入口；晚点Latepost、网络法实务圈仍未配置。
- Pilot：20个来源完成两个历史自然周回填；endpoint成功均为15/20，产出来源从11增至13。
- 日期质量：两周分别只有6条和4条候选具有明确入窗日期，通用HTML解析结果尚不能直接用于正式周报。
- 召回率：没有人工ground truth，当前只报告发现覆盖代理，真实召回率保持不可计算。
- 微信C2：50个全部生成调度并执行首轮扫描；8个有可执行入口，42个保持未配置。
- 微信C3：94个继续保持event-driven。

详细机器结果见同目录的 `source-endpoint-audit.json/csv`、`source-rollout-schedule.json`，以及本地 `reports/source-pilot/`、`reports/source-c2/`。
