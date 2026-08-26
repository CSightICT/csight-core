# Policy reranker slice analysis

```json
{
  "defect_type:BREAKAGE": {
    "hybrid_mrr_at_10": 0.5595238095238095,
    "hybrid_ndcg_at_10": 0.6081251620962924,
    "query_count": 7,
    "reranked_mrr_at_10": 0.5166666666666667,
    "reranked_ndcg_at_10": 0.6081251620962924
  },
  "defect_type:CONTAMINATION": {
    "hybrid_mrr_at_10": 0.55,
    "hybrid_ndcg_at_10": 0.6081251620962924,
    "query_count": 14,
    "reranked_mrr_at_10": 0.5380952380952381,
    "reranked_ndcg_at_10": 0.6111612673684451
  },
  "defect_type:FUNCTIONAL_FAILURE": {
    "hybrid_mrr_at_10": 0.5595238095238095,
    "hybrid_ndcg_at_10": 0.6081251620962924,
    "query_count": 7,
    "reranked_mrr_at_10": 0.5404761904761904,
    "reranked_ndcg_at_10": 0.6081251620962924
  },
  "defect_type:MISSING_COMPONENT": {
    "hybrid_mrr_at_10": 0.41666666666666663,
    "hybrid_ndcg_at_10": 0.5152163484100415,
    "query_count": 4,
    "reranked_mrr_at_10": 0.3958333333333333,
    "reranked_ndcg_at_10": 0.5380466912872549
  },
  "defect_type:PACKAGING_DAMAGE": {
    "hybrid_mrr_at_10": 0.5,
    "hybrid_ndcg_at_10": 0.5912352048230277,
    "query_count": 1,
    "reranked_mrr_at_10": 0.2,
    "reranked_ndcg_at_10": 0.4415801103577823
  },
  "defect_type:WRONG_ITEM": {
    "hybrid_mrr_at_10": 0.5476190476190477,
    "hybrid_ndcg_at_10": 0.6081251620962924,
    "query_count": 7,
    "reranked_mrr_at_10": 0.5404761904761904,
    "reranked_ndcg_at_10": 0.6081251620962924
  },
  "hard_negative": {
    "hybrid_mrr_at_10": 0.5383333333333333,
    "hybrid_ndcg_at_10": 0.5984120317958357,
    "query_count": 40,
    "reranked_mrr_at_10": 0.5125,
    "reranked_ndcg_at_10": 0.5980163255671794
  },
  "multiple_relevant": {
    "hybrid_mrr_at_10": 0.5383333333333333,
    "hybrid_ndcg_at_10": 0.5984120317958357,
    "query_count": 40,
    "reranked_mrr_at_10": 0.5125,
    "reranked_ndcg_at_10": 0.5980163255671794
  },
  "policy_type:EVIDENCE_REQUIREMENT": {
    "hybrid_mrr_at_10": 0.5354166666666667,
    "hybrid_ndcg_at_10": 0.5804661177385736,
    "query_count": 8,
    "reranked_mrr_at_10": 0.4895833333333333,
    "reranked_ndcg_at_10": 0.570431216382097
  },
  "policy_type:FUNCTIONAL_FAILURE": {
    "hybrid_mrr_at_10": 0.5520833333333334,
    "hybrid_ndcg_at_10": 0.5804661177385736,
    "query_count": 8,
    "reranked_mrr_at_10": 0.5041666666666667,
    "reranked_ndcg_at_10": 0.5651180321558298
  },
  "policy_type:HIGH_RISK_EXCEPTION": {
    "hybrid_mrr_at_10": 0.5520833333333334,
    "hybrid_ndcg_at_10": 0.5804661177385736,
    "query_count": 8,
    "reranked_mrr_at_10": 0.525,
    "reranked_ndcg_at_10": 0.570431216382097
  },
  "policy_type:MISSING_COMPONENT": {
    "hybrid_mrr_at_10": 0.41666666666666663,
    "hybrid_ndcg_at_10": 0.5152163484100415,
    "query_count": 4,
    "reranked_mrr_at_10": 0.3958333333333333,
    "reranked_ndcg_at_10": 0.5380466912872549
  },
  "policy_type:RETURN_EXCHANGE": {
    "hybrid_mrr_at_10": 0.5520833333333334,
    "hybrid_ndcg_at_10": 0.5804661177385736,
    "query_count": 8,
    "reranked_mrr_at_10": 0.49375,
    "reranked_ndcg_at_10": 0.570431216382097
  },
  "policy_type:SHIPPING_DAMAGE": {
    "hybrid_mrr_at_10": 0.75,
    "hybrid_ndcg_at_10": 0.602191198794243,
    "query_count": 2,
    "reranked_mrr_at_10": 0.225,
    "reranked_ndcg_at_10": 0.3528241164651866
  },
  "policy_type:WRONG_ITEM": {
    "hybrid_mrr_at_10": 0.6041666666666666,
    "hybrid_ndcg_at_10": 0.6087529159299382,
    "query_count": 8,
    "reranked_mrr_at_10": 0.5145833333333333,
    "reranked_ndcg_at_10": 0.570431216382097
  },
  "scenario:parent_exception": {
    "hybrid_mrr_at_10": 0.5555555555555556,
    "hybrid_ndcg_at_10": 0.5939082885094626,
    "query_count": 6,
    "reranked_mrr_at_10": 0.38055555555555554,
    "reranked_ndcg_at_10": 0.526301107978517
  },
  "scenario:tenant_version_filter": {
    "hybrid_mrr_at_10": 0.5352941176470588,
    "hybrid_ndcg_at_10": 0.5992068100228427,
    "query_count": 34,
    "reranked_mrr_at_10": 0.5357843137254902,
    "reranked_ndcg_at_10": 0.6106719522004727
  },
  "tenant:csight-demo-brand": {
    "hybrid_mrr_at_10": 0.5416666666666667,
    "hybrid_ndcg_at_10": 0.6021534091574668,
    "query_count": 20,
    "reranked_mrr_at_10": 0.5258333333333333,
    "reranked_ndcg_at_10": 0.596953688721926
  },
  "tenant:csight-demo-retail": {
    "hybrid_mrr_at_10": 0.5349999999999999,
    "hybrid_ndcg_at_10": 0.5946706544342046,
    "query_count": 20,
    "reranked_mrr_at_10": 0.49916666666666665,
    "reranked_ndcg_at_10": 0.5990789624124329
  }
}
```
