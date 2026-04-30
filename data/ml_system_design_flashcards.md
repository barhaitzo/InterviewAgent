# ML System Design — Flashcards

Format: **Concept** → *When to use* → *Tradeoff / what you give up*

Drill both directions: given the concept, state when-to-use and tradeoff. Given a scenario, name the concept.

---

## 0. ML fundamentals (know cold)

**Overfitting** → Any supervised ML task → Low train loss, high val loss; model memorized noise. Fixes: more data, L2/L1, dropout, early stopping, simpler model, augmentation, ensembling.

**Underfitting** → Any supervised ML task → Both train and val loss high and flat; model too weak. Fixes: bigger model, better features, less regularization, train longer, better optimizer.

**Bias-variance tradeoff** → Always when explaining model error → Bias = systematic underfit; variance = memorization of noise; irreducible = label noise. Reduce one → other usually grows. More data and good regularization break the tradeoff.

**L2 regularization (weight decay)** → Default DNN regularization; any linear model → Adds `λ·Σw²` to loss; shrinks weights toward (but not to) zero. Tradeoff: doesn't do feature selection (use L1 for that); needs λ tuning.

**L1 regularization (lasso)** → Sparse feature selection; high-dim linear models (ads CTR) → Drives weights to exactly zero; picks features implicitly. Tradeoff: harder to optimize (non-smooth); less stable than L2.

**Dropout** → Any DNN prone to overfitting → Zeros random activations during training; ensemble effect; off at inference. Typical rate 0.1–0.5. Tradeoff: slower convergence; not needed if you have lots of data.

**Early stopping** → Any iterative training (DNN, GBDT) → Stop when val loss stops improving. Cheap, effective. Tradeoff: need val set; picks imperfect stopping point.

**Batch normalization** → Deep CNNs, some DNNs → Normalizes activations per batch; speeds training, slight regularization. Tradeoff: batch-size-dependent behavior; awkward for small batches (use LayerNorm for transformers).

**Cross-entropy loss** → Classification with probabilistic outputs (CTR, harmful content, etc) → Penalizes confidently wrong predictions sharply; pairs with sigmoid/softmax. Tradeoff: sensitive to label noise.

**MSE vs MAE vs Huber** → Regression → MSE = penalizes outliers quadratically (sensitive); MAE = robust to outliers (less smooth gradient); Huber = L2 for small errors, L1 for large (best of both). Pick by outlier sensitivity.

**Focal loss** → Extreme imbalance (1:1000+ like object detection, some fraud) → Down-weights easy examples so model focuses on hard positives. Tradeoff: extra hyperparameter (γ); unnecessary for mild imbalance.

**Contrastive / triplet / InfoNCE loss** → Embedding / metric learning (two-tower models) → Pull positives close, push negatives far. Tradeoff: hard-negative mining matters; easy negatives teach nothing.

**Adam / AdamW** → Default DNN optimizer → Adaptive per-parameter LR, robust, fast convergence. AdamW decouples weight decay properly. Tradeoff: sometimes final accuracy lags tuned SGD-momentum.

**SGD with momentum** → Image models, when tuned; small models → Often best final accuracy if you tune LR schedule. Tradeoff: tuning-sensitive; slower to iterate on.

**Adagrad / FTRL** → Sparse high-dim features (ads, recsys CTR) → Per-feature adaptive LR; handles rare features well. Tradeoff: LR monotonically decays (Adagrad) — eventually stops learning.

**Precision vs Recall** → Any binary classifier with threshold → Precision = of flagged, how many correct; Recall = of actual positives, how many caught. Threshold tradeoff. F1 = harmonic mean when you need one number.

**Train / val / test split** → Any supervised ML → Train fits, val tunes, test measures (once, at the end). Never tune on test. For time-series: temporal split only; random splits leak future.

**Temporal (walk-forward) CV** → Any time-series / production ML → Train on past weeks, validate on next. Prevents leakage. Tradeoff: less data efficiency than k-fold; required anyway.

**Parametric vs non-parametric** → When asked about model complexity → Parametric (LR, DNN) = fixed params; non-parametric (kNN, decision trees to a degree) = grows with data. Parametric scales to huge data; non-parametric captures arbitrary shapes but slow at scale.

**Gradient descent intuition** → Any training question → Compute loss, backprop for gradients, step weights opposite gradient by LR. Variants: mini-batch, SGD, Adam. Vanishing gradients in deep nets → ReLU, residual connections, normalization, careful init.

---

## 1. Framework & framing

**Business objective vs ML objective** → Use whenever framing a problem → Business = what the company wants (revenue, engagement, safety); ML = the loss function you optimize. They diverge (clickbait maxes CTR but hurts satisfaction). Always name guardrails.

**Guardrail metric** → Use alongside any primary metric → Catches regressions in dimensions the primary metric ignores. E.g., CTR primary, complaint-rate / unfollow / session-length / latency as guardrails. Without them you ship harmful wins.

**Ranking vs classification vs regression framing** → Ranking when ordering matters (feeds, search); classification when binary decision (CTR, harmful content); regression when numeric target (ETA, price) → Ranking needs ranking metrics (NDCG), specialized losses (pairwise, listwise), and different eval.

**Multi-task learning** → When you care about multiple outcomes from one decision (feed: likes + shares + watch + reports) → Shares representations, fewer models to maintain. Tradeoff: task conflict (one task's loss harms another) → mitigated with MMoE. Loss weighting tuning is non-trivial.

---

## 2. Two-stage architecture

**Candidate generation (retrieval)** → When catalog is too large to score with heavy model (millions+) → Fast, cheap, high recall; accepts low precision. Tradeoff: if you miss a good item here, ranker can't save it. Always use multiple channels in parallel and union.

**Two-tower model for retrieval** → When you need sub-linear user-item retrieval over huge catalogs → User tower + item tower → dot product; item embeddings pre-computed and indexed in ANN. Tradeoff: no feature crosses between user and item, so less expressive than ranker. That's fine because ranker handles it.

**ANN (approximate nearest neighbor) index** → When you need vector similarity search at scale (millions–billions of items, ms latency) → HNSW, FAISS, ScaNN. Tradeoff: gives approximate top-K (recall <100%) in exchange for sub-linear query time. Tune recall/latency per problem.

**Collaborative filtering** → When you have interaction data and want a simple, strong baseline for recs → Matrix factorization on user-item interactions; no content features needed. Tradeoff: struggles with cold start (new users/items); less expressive than deep models.

**Ranking model** → Stage 2, scores ~thousands of candidates with richer features → Expensive per-item but only runs on shortlist. Multi-task DNN / GBDT / Wide & Deep. Tradeoff: latency-budget bound; you can't go arbitrarily deep.

**Re-ranking** → Stage 3, applies diversity / business rules / policy / ad blending → Ensures variety, respects constraints not in the objective. Tradeoff: each rule you add dilutes the model's learned optimum; validate with A/B.

---

## 3. Data & features

**Missing negatives problem** → Any implicit feedback setting (clicks, watches) → A non-click isn't necessarily a dislike — the user may not have seen the item. Fix: use impression logs to construct true negatives (shown but not engaged) or random negatives. Pure "didn't interact" labels are noisy.

**Position bias** → Any system where items are shown in a ranked order (feeds, search, ads) → Top-position items get more clicks regardless of quality, biasing training data. Fix: include position as a training feature, set to a fixed value at serving. Known as "position debiasing."

**Selection bias / feedback loops** → Any recommender trained on its own past outputs → Model's recommendations become its training data → reinforces its own biases → filter bubbles, popularity bias. Fix: exploration slots (epsilon-greedy, Thompson sampling), inverse propensity scoring.

**Label leakage** → When features accidentally contain future info → Looks great offline, fails live. Fix: always split temporally, audit feature pipeline for "future" signals. Critical: train on week 1–3, validate on week 4.

**Data buckets (supervised / semi-supervised / unsupervised)** → Mention all three when discussing training data → Supervised = labeled; semi-supervised = weak/pseudo labels, sparse ground truth; unsupervised = pre-training on raw clicks/co-views without labels. Mentioning semi/unsup is senior signal because labels are expensive.

**Class imbalance (CTR)** → When positive class is <5% (clicks, conversions, harmful content) → Accuracy is misleading. Fix training: downsample negatives or upweight positives. Fix metrics: use PR-AUC, log-loss, calibration. Fix serving: recalibrate probabilities if you downsampled.

**Feature freshness hierarchy** → Always when discussing features → Batch (hourly/daily): user long-term profile, item stats. Near-real-time (minutes): trending, session features. Real-time (per-request): current session, last action. Picking the right tier for each feature is production-critical.

**Feature store** → When you have a production ML system with >1 model → Serves features consistently to training and inference pipelines. Tradeoff: extra infra; but the alternative is train-serve skew (silent bugs from divergent feature computation).

**Train-serve skew** → Any time features are computed differently in training vs serving → Classic silent bug: model great offline, bad in prod. Fix: feature store; or serve-time feature logging used to generate training data.

**Embeddings for categorical features** → When categorical has high cardinality (user_id, item_id, word) → Learned dense representations; compact, capture similarity. Tradeoff: huge embedding tables (GBs–TBs at scale) need sharding; cold-start new IDs need fallback.

**Hashing trick** → When cardinality is so high the embedding table won't fit (hundreds of millions of IDs) → Hash IDs to N buckets, share embeddings per bucket. Tradeoff: collisions (two items share an embedding) — usually fine because rare items collide with rare items.

**Pre-trained content embeddings** → When you have unstructured content (text, image, video) → Use BERT/CLIP/ViT/ResNet/VideoMAE to extract dense features. Tradeoff: generic embeddings may miss domain specifics; fine-tune if you have data, otherwise they're a strong starting point for cold-start.

---

## 3b. Feature transformations (raw → engineered)

**Normalize by a denominator** → Whenever a raw count is scale-confounded → `likes` → `like_rate = likes / impressions`. Removes popularity as a confound. Tradeoff: introduces variance when denominator is small (see smoothing).

**Log-transform long-tailed features** → Power-law distributed features (view counts, follower counts, prices) → `log1p(x)`. Makes linear models and DNNs handle them better. Tradeoff: tree models don't need it.

**Bayesian smoothing / shrinkage** → Low-sample rate estimates (new items, rare segments) → `(clicks + α·prior) / (impressions + α)`. Shrinks toward prior when sample size low. Tradeoff: needs choosing α and prior; empirical Bayes can automate.

**Bucketing / discretization** → Continuous features with non-monotonic effect on target (age, time of day) → Quantile buckets + embedding per bucket. Captures non-linearity in linear models. Tradeoff: loses resolution; bucket boundaries matter; quantile > uniform for skewed features.

**Multi-scale time-window aggregates** → Any behavioral / engagement feature → `views_1h`, `views_24h`, `views_7d`, `views_30d` + ratios. Captures multi-scale patterns and trajectory. Tradeoff: more features = more compute; diminishing returns.

**Recency decay** → Past interactions where newer ones matter more → `Σ exp(−Δt/τ)` with half-life τ tuned per use case. Smoother than hard windows. Tradeoff: picking τ is a hyperparameter.

**Cross features** → When two features interact multiplicatively (user_lang × item_lang) → Explicit cross inside the model or as input. Wide & Deep literally exists for this. Tradeoff: combinatorial explosion if applied broadly; DNNs learn some crosses automatically.

**Target encoding** → Very high-card categorical (zip, user_id) for linear models → Replace category with `mean(target | category)`. Compact, effective. Tradeoff: **leakage risk**; must use out-of-fold computation or strictly-historical data.

**Missing-value indicator** → When missingness is itself informative → Add `was_missing` boolean alongside imputed value. Tradeoff: more features; only helpful when missingness correlates with label.

**Outlier clipping / winsorization** → Features with rare extreme values → Clip to [1st percentile, 99th percentile]. Prevents a few outliers dominating loss. Tradeoff: loses information about true outliers; tune threshold.

**"Num_likes" → senior feature drill** → Practice example → Raw → like_rate → log(like_rate) → smoothed with prior → normalized within category → multi-window → percentile rank. Memorize this progression.

---

## 4. Modeling

**Baseline first** → ALWAYS in interviews → Popularity, rule-based, logistic regression with hand-crafted features, or classical CF. Establishes yardstick, reveals whether complexity is justified. Skipping this is a red flag.

**Logistic regression / GBDT for CTR** → When you have strong hand-crafted features, tabular data, need speed/interpretability → Fast, interpretable, no GPU. Tradeoff: less expressive than DNN; can't learn high-order feature crosses automatically (LR) or handle embeddings well (GBDT).

**Wide & Deep** → CTR-style problems with both memorization (specific feature combos matter) and generalization needs → Wide = linear with crosses (memorize); Deep = DNN over embeddings (generalize). Tradeoff: manual feature cross engineering for the wide part.

**DCN / DCN-v2 (Deep & Cross)** → When you want the model to learn feature crosses automatically → Cross layers explicitly compute higher-order interactions. More principled than manual crosses. Tradeoff: more complex; tune cross depth.

**DeepFM** → Similar to Wide & Deep but replaces wide with factorization machines → Learns pairwise feature crosses automatically; no manual engineering. Tradeoff: fixed to pairwise crosses (unless stacked).

**DIN / DIEN** → When user has a meaningful history of past items and you're ranking new candidates → Attention over user history items, weighted by relevance to the current candidate. Tradeoff: more compute per prediction; sequence length bounded.

**Transformer sequence models for recs (SASRec, BST)** → When user sessions / sequences are long and order matters → Self-attention over interaction history; strong for session-based recs. Tradeoff: expensive at long sequences; needs careful handling of item embeddings.

**MMoE (Multi-gate Mixture of Experts)** → Multi-task ranking with conflicting tasks → Experts shared across tasks; per-task gates choose which experts each task uses. Tradeoff: more parameters; harder to tune than vanilla shared-bottom.

**Multi-task weighted loss** → When you have multiple heads (watch, like, share, skip) → Weighted sum: `L = Σ w_i · L_i`. Training weights ≠ serving weights (training balances learning; serving encodes business objective). Tradeoff: weight tuning is a search problem; uncertainty weighting is a principled approach.

**Distillation** → When you have a heavy teacher model but need a fast serving model → Train small student to match teacher's output distribution. Tradeoff: usually a small accuracy drop; done when latency/cost forces it.

**Quantization (fp16, int8)** → When inference latency/throughput is a bottleneck → 2–4× speedup. Tradeoff: small accuracy degradation; some ops don't quantize cleanly; post-training vs quantization-aware training.

**Online learning / FTRL** → When distributions shift fast (ads, trending content) → Continuous updates on streaming events; FTRL (Follow-The-Regularized-Leader) scales to billions of sparse features. Tradeoff: harder to debug; needs careful monitoring for drift; rollback is harder.

---

## 5. Evaluation

**Offline vs online evaluation** → Both, always → Offline = fast iteration on historical data; online = true measurement on real users. Always use both; they diverge (offline wins don't always ship).

**NDCG** → Ranking problems where position matters → Discounts lower positions, normalizes per query. Standard for search and top-k recs. Tradeoff: needs graded relevance or you can use binary; sensitive to K choice.

**AUC / ROC-AUC** → Binary classification, usually balanced → Threshold-independent; measures ranking ability. Tradeoff: can be misleading on heavily imbalanced data — use PR-AUC instead.

**PR-AUC (Precision-Recall AUC)** → Binary classification, imbalanced (CTR, fraud, harmful) → Focuses on positive class performance. Tradeoff: less intuitive than AUC; baseline depends on class rate.

**Log loss / cross-entropy** → Probabilistic classification where calibration matters (ads) → Penalizes confident wrong predictions more than weakly wrong. Tradeoff: sensitive to outliers.

**Calibration (ECE, reliability diagrams)** → Anywhere predicted probabilities are used for decisions (ads auctions, risk scoring) → Predicted P(click)=0.3 should mean 30% actual click rate. Tradeoff: most DNNs are miscalibrated out of the box; fix with Platt / isotonic post-hoc.

**A/B testing** → Always, to validate changes → Gold standard. Randomize users (or sessions), measure primary + guardrails. Tradeoff: slow (1–4 weeks), needs lots of users, novelty effects early.

**Interleaving** → Fast ranker quality comparison → Mix rankers' outputs within a single user's results; compare per-impression. Tradeoff: only works for ranking; measures relative quality, not absolute impact.

**Shadow mode** → Pre-launch validation of new model → Run new model in prod, don't use its output; compare predictions, measure latency. Tradeoff: no user-impact signal; only validates safety and perf.

**Counterfactual / replay evaluation** → When online test is expensive or risky → Replay logged requests through the new ranker and estimate metric changes. Tradeoff: biased by selection bias — only covers items actually logged.

**Temporal split, not random** → Any time-series ML → Train on past, evaluate on future. Random splits leak future info. Tradeoff: can't do k-fold CV naively; use rolling windows instead.

**Novelty effect** → A/B testing anything new → Users respond to newness, inflating short-term metrics; fades over 1–2 weeks. Fix: run longer; measure late-week metrics only.

**Guardrail metrics in A/B** → Every experiment → Latency, error rate, complaints, long-term retention. Treatment must not regress these. Tradeoff: more metrics = more chances of false-positive regression; use a principled threshold.

---

## 6. Inference & production

**Feature hydration fanout** → Any online-ranking system → For (user, N candidates), you fetch features for all N from feature store — can be the biggest latency contributor. Mitigations: batching, caching, local pre-aggregation.

**Caching in ML serving** → When requests repeat (same user, short TTL) → Cache candidate lists, feature fetches, or full predictions. Tradeoff: stale content if TTL too long; cache invalidation complexity.

**Batching inference** → GPU serving → Group requests into one forward pass for 5–50× throughput. Tradeoff: adds up-to-batch-window latency; usually a few ms.

**Model versioning & shadow → canary → full rollout** → Every production ML system → Shadow (no user impact) → canary (1–5% of traffic) → full rollout. Tradeoff: takes time; worth it to avoid incidents.

**Drift monitoring** → Every production ML system → Feature distribution, prediction distribution, label distribution (when labels arrive) drift over time. Alert on anomalies; retrain. Tradeoff: labels lag (clicks fast; conversions slow).

**Retraining cadence** → Every production ML system → Daily/weekly batch retrains are typical; online learning for fast-moving. Tradeoff: more frequent = more compute, more variance; less frequent = staler model.

**Cold start (user)** → Any recommender → Fall back to popularity / demographic segment / onboarding signals; increase exploration early. Tradeoff: worse initial experience; fades as history accumulates.

**Cold start (item)** → Any recommender → Use content embeddings only (no interaction history); seed exposure via exploration bucket. Tradeoff: new items may underperform initially; mitigated by sufficient seed exposure.

**Exploration (epsilon-greedy / Thompson sampling)** → Systems with feedback loops → Devote a budget (1–5%) to random or less-certain items to break feedback loops and discover new good items. Tradeoff: short-term metric dip (exploration is noisy); long-term health benefit.

**Diversity in re-ranking (MMR)** → Feeds / recs where diversity matters → Maximal Marginal Relevance: rank items by relevance, subtract similarity to already-ranked. Tradeoff: hard to tune diversity weight; may reduce relevance metrics.

---

## 6b. Model risks & debugging

**Anticipated-risk checklist (say 3–4 proactively in modeling phase)** → Every ML system design interview → Pick from: selection bias, clickbait optimization, position bias, cold start, feedback loop, drift, miscalibration, adversarial gaming, train-serve skew. Name mitigation for each. Meta calls this out explicitly.

**"Overfit a batch" debugging test** → First thing to try when training seems broken → Can the model drive loss to ~0 on 1000 examples? If no → architecture bug (wrong loss, broken gradients, frozen weights). If yes → capacity or feature problem.

**Loss curve diagnostics** → When told "model isn't working well" → Train↑Val↑ = underfit; Train↓Val↑ = overfit; both NaN = instability (LR too high); train erratic = bad data or LR; one-class predictions = class collapse.

**Slice-based error analysis** → Any post-training diagnosis → Break metric down by user cohort, item category, device, country, new vs returning. Overall 85% can hide 50% on a critical segment. Meta interviewers love this.

**Feature importance audit** → When diagnosing a trained model → Permutation importance or SHAP reveals driver features. Implausibly high importance = leakage. Low importance on expected drivers = encoding issue.

**Train-serve skew diagnosis** → "Great offline, bad online" → Log features at both ends, compare row-by-row. Check: feature definitions, aggregation windows, null handling, time zones, preprocessing order.

**Distribution shift check** → Any model degrading in production → Plot each feature's distribution train vs live. Mismatches = data drift or pipeline bug. Predictions distribution drift = model or input drift.

**Rollback-first discipline** → Live regression → Roll back before diagnosing. Never debug live. Tradeoff: takes courage; delays the next attempt. Worth it.

**Retraining cadence choice** → Every production ML system → Fast-drift (ads, trends) → hourly/online. Stable (long-term recs) → weekly. Driven by drift rate and data volume. Tradeoff: frequent = compute cost, variance; infrequent = stale model.

**"What do you do if it doesn't work?" answer template** → Meta's literal question → "First check whether it's a data, model, or serving issue. Look at loss curves for over/underfit. Slice by segment. Overfit-a-batch test. If offline good but online bad, suspect train-serve skew — log features at both ends." Memorize this.

---

## 7. Red flags & green flags (interview self-check)

**🟢 "Let me clarify before I design"** → Always opens a framing phase → Interviewers look for this explicitly. Skipping = junior signal.

**🟢 "Let me start with a baseline"** → Always before proposing a DNN → Grounds the conversation in tradeoffs, not hype.

**🟢 "The naive ML objective is X, but the business objective is Y, so I'd propose Z"** → In Framing → Instant senior signal. Shows you translate, not just transcribe.

**🟢 "Before I commit, here are two options and the tradeoff"** → In modeling → Shows breadth and judgment.

**🟢 "Three risks with this model, and mitigations: ..."** → In modeling phase, unprompted → Meta explicitly grades on risk anticipation; proactive naming = senior signal.

**🟢 "If it's not performing well, I'd first check loss curves, then slice by segment, then suspect train-serve skew"** → When interviewer asks debugging → Having a structured diagnostic answer = senior signal.

**🟢 "Give me a few seconds to think"** → When stuck → Better than bluffing. Interviewers respect it.

**🔴 Drawing boxes in minute 1** → Before clarifying → Skipped framing → junior signal.

**🔴 Feature dump** → Listing 15 features without hypotheses → Looks like memorization, not reasoning.

**🔴 Latest-paper-only modeling** → Proposing one hot model without baseline or alternatives → Shows you follow hype, not tradeoffs.

**🔴 Skipping online eval** → "Offline AUC is great, done" → Major red flag. Offline wins don't always ship.

**🔴 No guardrails** → Named only one metric → Interviewer will probe; you should've pre-empted.

**🔴 Bluffing on unknowns** → Inventing details when asked → Much worse than saying "I don't know, but here's how I'd reason about it."

---

## 8. Rapid-fire numbers to know

- 1 day ≈ 10⁵ seconds (86,400)
- QPS ≈ DAU × req/user/day / 10⁵
- Peak QPS ≈ 2–3× average
- Online ranking latency budget: typically 100–300 ms end-to-end
- Ad CTR typical: 1–5%
- Reels/Feed watch-through rate: order of 10–30% (depends on definition)
- Retrieval stage: ~10⁹ → ~10³–10⁴ candidates
- Ranking stage: ~10³ → ~10¹ items shown
- Embedding dimension: typically 64–512
- Embedding table size: billions of IDs × hundreds of dimensions = hundreds of GB → needs sharding
- Retraining cadence: hourly (ads, fast drift) to weekly (stable recs)

---

## 9. Quick-pattern recognition

| Prompt shape | Default framing | Default architecture |
|---|---|---|
| "Design recommendations for X" | Multi-task ranking; watch/like/share/skip heads | 2-stage: two-tower retrieval + MMoE ranker |
| "Design feed ranking" | Multi-task ranking; effortful interactions weighted | No heavy retrieval (graph-bounded); MMoE ranker |
| "Design ad CTR prediction" | Calibrated binary classification | Wide & Deep / DCN / DeepFM; online learning; calibration |
| "Design search ranking" | Ranking; query-doc relevance | Lexical + dense retrieval union → LTR ranker |
| "Design PYMK / connections" | Ranking; P(accept connection) | Graph retrieval (FoF) → DNN ranker on graph+profile features |
| "Design harmful content detection" | Multi-label classification | Modality-specific classifiers → ensemble → policy + HITL |
| "Design fraud / bot detection" | Binary / anomaly, adversarial | Graph + sequence + device features; anomaly + supervised |
| "Design ETA prediction" | Regression (or calibrated quantile) | GBDT or DNN on route/traffic features; multi-stage |
| "Design dynamic pricing" | Regression or bandit/RL | Bandit framework; demand-elasticity features |

---

## 10. Task type → go-to model (drill this)

Format: **Task type** → *baseline* → *production default* → *loss* → *key metric*. Given a task, name all four within 5 seconds.

**Binary classification (CTR, harmful, fraud, spam)** → Logistic regression + L2 → GBDT (tabular) or Wide & Deep / DCN-v2 (huge embeddings) → Binary cross-entropy → AUC / PR-AUC / log-loss

**Multi-class classification (topic, intent)** → Softmax LR → DNN with softmax head; pre-trained encoder + head for text/image → Categorical cross-entropy → Top-k accuracy / macro-F1

**Multi-label classification (content moderation: hate+violence+spam as separate labels)** → Per-label binary → Shared-encoder DNN + N sigmoid heads → Sum of BCEs → Per-label F1 + macro-F1

**Regression (ETA, price, demand, rating)** → Linear regression → GBDT (tabular) or DNN (with sequences/embeddings) → MSE / MAE / Huber; pinball for quantiles → MAE / RMSE / MAPE

**Ranking / learning-to-rank (search, feed, ads)** → Pointwise classifier → Pointwise multi-task DNN (Meta-style) or LambdaMART (GBDT) → BCE per task / pairwise / listwise → NDCG@k / MAP / MRR

**Retrieval (candidate gen, semantic search)** → Collaborative filtering / BM25 → Two-tower DNN + ANN index (HNSW/FAISS) → Contrastive / InfoNCE / triplet → Recall@k

**Sequence / session modeling (next-item, user behavior)** → Most-recent-item / GRU4Rec → Transformer-based (SASRec, BST) → Cross-entropy over vocab or contrastive → Recall@k, next-item accuracy

**Text classification** → TF-IDF + LR → Fine-tuned BERT-family (distilled at scale) → Cross-entropy → F1 / accuracy

**Text generation / summarization** → Extractive heuristic → Decoder-only LLM or encoder-decoder (T5); RAG for grounded gen → Cross-entropy (teacher forcing) → ROUGE / BLEU / human eval

**Image classification** → Features + LR → ViT or ResNet fine-tuned → Cross-entropy → Top-1 / top-5 accuracy

**Object detection** → — → YOLO (fast) / Faster R-CNN (accurate) / DETR (transformer) → Focal + box regression → mAP

**Segmentation** → — → U-Net (medical/simple) / Mask R-CNN (instance) → Dice / BCE / focal → IoU / Dice

**Image/video embedding (retrieval)** → — → CLIP or pre-trained visual backbone → Contrastive → Recall@k

**Graph node classification / link prediction (PYMK)** → Graph features + GBDT → GraphSAGE / GAT → Cross-entropy (node) or BCE (edge) → Accuracy (node) or Hits@k / MRR (edge)

**Anomaly / outlier detection (fraud, intrusion)** → Isolation Forest / LOF (unsup) → Supervised DNN with focal loss (if labels) or autoencoder + classifier hybrid → Focal / reconstruction → PR-AUC

**Time series forecasting** → ARIMA / exponential smoothing → LightGBM with lag features (often wins) or Temporal Fusion Transformer → MSE / MAE / pinball → MAPE / MASE

**Clustering (segmentation, discovery)** → k-means → Pre-trained encoder → HDBSCAN → — → Silhouette / downstream task metric

**Contextual bandit (ads bidding, exploration)** → ε-greedy → LinUCB / Thompson sampling → Regret minimization → Cumulative regret / reward

**The interview moment this unlocks:** the instant you say "this is a [task type]" in Phase 1c, the rest of Phase 4 pre-loads in your head. You don't hunt for a model — you already know the family and the alternative.
