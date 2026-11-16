"""테스트 전용 예시 기준값 — 0.60.x까지 도구 안에 있던 관행·우리 규칙 값. 0.61.0부터 도구는 이 값을 갖지 않고 rules·screens로 받는다
(실제 값·출처는 조문 MCP transfer_pricing_guide). 기존 기댓값을 같은 기준으로 확인하려고 테스트에서만 넘긴다."""
EX_RULES = {"mix_max_diff": 0.20, "ratio_low": 0.5, "ratio_high": 2.0, "ppe_abs_tol": 0.05, "rnd_abs_tol": 0.01,
            "advert_mult": 3.0, "advert_abs_tol": 0.03, "sga_mult": 2.0, "sga_abs_tol": 0.05, "coverage_min": 0.8, "coverage_max": 1.2,
            "related_review": 0.20, "unknown_review_count": 3, "mix_unverified_review": 0.10, "loss_review_years": 2}
EX_SCREENS = {"independence_pct": 25, "independence_bvd_reject": ["C", "D", "U"], "loss_years": 2, "rnd_max": 0.03, "adv_max": 0.05,
              "related_max": 0.25, "segment_min": 0.75, "special_flags": ["start_up", "bankruptcy", "restructuring", "merger", "delisted"],
              "outlier_k": 1.5}
