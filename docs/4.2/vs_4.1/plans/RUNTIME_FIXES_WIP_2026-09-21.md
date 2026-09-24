# DeepSeek 运行问题修复工作中断记录（2026-09-21）

> 状态：**已由后续收尾完成。** 现行说明与验收见 [../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md](../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md) 与 [../changes/CHIRP_ROW_CONTRACT_2026-09-21.md](../changes/CHIRP_ROW_CONTRACT_2026-09-21.md)。本文保留中断时的上下文，不再作为待办清单。

原先第 5 节的恢复顺序已执行：可见性旧夹具已迁移，混合测站有规范化 / campaign / GUI 测试，`pulse_batch_size=1` 走 `batch_kernel`，`geometry.py` 拒绝非整 `fast_sample_count`，D1–D5 与 T1 已写入行为文档和守卫测试。对抗性审查指出的混合选时未钉住、直角坐标斜纹条件、以及过期手册段落已在同一轮补上。

反演算法、死代码清理、以及 `LOGIC_STABILITY_FIX_PLAN_2026-09-21.md` 的批次 A–F 仍不在本文件范围内。
