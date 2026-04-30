# ML System Design Crash Course — Meta-focused, ~13 days

**Source material:** Educative "Machine Learning System Design" + "Grokking the Machine Learning Interview", Grokking the System Design Interview (for backend fundamentals), HelloInterview ML System Design in a Hurry, and public reports from recent Meta E5/E6 ML system design loops.

---

## Part 0 — What Meta is actually grading you on (read first)

Before anything else, internalize this. It changes how you spend the 45–60 minutes.

**The #1 insight from recent Meta ML system design debriefs:** the majority of the interview should be spent on **ML modeling and tradeoffs**, not on infrastructure. Meta wants to know if you can reason about:

1. **Business → ML objective translation.** Can you turn "improve Reels engagement" into a precise ML problem (ranking with multi-task heads predicting watch probability, share probability, skip probability, with a weighted loss)? The cleaner this translation, the more senior you look.
2. **Data and features.** Where do labels come from, what are the implicit vs explicit signals, how do you handle missing negatives (non-clicks aren't really negatives), how do you prevent leakage, how do you keep features fresh.
3. **Model choice and tradeoffs.** A simple baseline (logistic regression on hand-crafted features, or popularity) → a stronger model (GBDT, two-tower, deep & cross). Can you compare families and justify your choice against latency/cost/data constraints?
4. **Evaluation.** Offline → online. NDCG offline, A/B on CTR + guardrails (watch time, retention, complaints). Why offline and online can diverge.
5. **Production realities.** Feature freshness, feedback loops, position bias, cold start, drift, retraining cadence.

Everything else — load balancers, how the feature store is sharded, Kafka partitioning — is *secondary*. You should know the vocabulary so you can gesture at it when asked, but you should not be driving the conversation there.

**Seniority signal:**

- **Junior:** dumps a list of features, picks the newest model from a blog post, forgets online eval, hand-waves on production.
- **Mid:** has a framework, covers all phases, but stays shallow on tradeoffs.
- **Senior (E5):** drives the business-objective clarification, picks baselines first, goes deep on one or two areas of expertise, surfaces tradeoffs proactively.
- **Staff (E6):** frames the *outer loop* (feedback, creator incentives, platform health), anticipates failure modes (clickbait, filter bubbles, gaming), talks about measurement design (interleaving, shadow mode).

**Rule of thumb for time allocation in a 45-min interview:**

| Phase | Time | Meta priority |
|---|---|---|
| Problem framing (business → ML objective) | 5–7 min | ⭐⭐⭐ |
| High-level architecture sketch | 2–3 min | ⭐ |
| Data and features | ~10 min | ⭐⭐⭐ |
| Modeling (baselines → proposed model → architecture) | ~10 min | ⭐⭐⭐ |
| Inference and evaluation (offline + online + production) | ~7 min | ⭐⭐ |
| Deep dives (driven by interviewer) | remaining | ⭐⭐ |

**Mapping to Meta's 5 published focus areas (from the career page):**

| Meta focus area | Covered in |
|---|---|
| **Problem Navigation** (business context → ML decisions) | Phase 1 (Framing) |
| **Training Data** (collection, constraints, risks) | Phase 3a |
| **Feature Engineering** (relevant features, importance, *normalization/smoothing/bucketing*) | Phase 3b, Phase 3b-2 |
| **Modeling** (justify choice, explain training, *anticipate and mitigate risks*) | Phase 4, especially 4f |
| **Evaluation & Deployment** (consistent eval, metric choice, debugging) | Phase 5, especially 5e |

Plus: **Phase 0** — ML theory fluency (overfitting, regularization, bias/variance) that Meta says to brush up on before the interview.

**Communication habits the E5 hires reported:**

- "Let me clarify the requirements first" before drawing anything
- "I'll outline the high-level design before diving deeper"
- Announcing your time allocation: "I'll spend ~5 min on framing, then sketch, then go deep on the model"
- When stuck: "Give me five seconds to think" — actually valuable, interviewers respected it
- Proactively calling out tradeoffs: "I'm choosing X over Y because [cost/latency/data]; if [condition changed], I'd go with Y"

---

## Part 1 — The universal framework (memorize this)

This is the skeleton you apply to **every** ML system design question. When you get asked "design X", this is the order. I call it **FHDMIE**:

1. **F**rame — business goal → ML objective
2. **H**igh-level — sketch the pipeline (2 min, don't fuss)
3. **D**ata & features — sources, labels, feature engineering, encodings
4. **M**odeling — baseline first, then model(s), then architecture
5. **I**nference — how it's served, latency, cost, caching, optimization
6. **E**valuation — offline metrics, online A/B, guardrails, monitoring

Then **Deep Dives** on whatever the interviewer pulls.

I'll walk through each phase below. Every Part-2 case study will reference back to these phase definitions.

**Note:** before the phases, there's a **Phase 0** — core ML theory you need to have loaded before the interview. It's not a phase you execute in the interview; it's prerequisite knowledge the interviewer assumes. I put it first because it needs to be fluent, not fresh.

---

## Phase 0 — ML fundamentals you must be fluent in

Meta's career page says this directly: *"Brush up on basic ML theory and algorithm details. Be comfortable with concepts like overfitting and regularization."* Strong system design can be undermined in 30 seconds by a shaky answer on bias/variance. This section is what you're expected to be fluent in before walking in.

### The bias–variance tradeoff

Two sources of error in any model:
- **Bias:** the model is too simple to capture the pattern → systematically wrong → **underfits**. High train loss AND high validation loss.
- **Variance:** the model is too flexible and memorizes noise in the training data → **overfits**. Low train loss, high validation loss — the gap is the symptom.
- **Irreducible error:** noise in the labels; no model can beat it.

The tradeoff: reducing one usually increases the other. Deep models with good regularization are one way modern ML breaks the tradeoff; more data is the other (variance shrinks with data).

**Interview test:** "I trained a model, train accuracy is 99%, validation is 62%. What's going on?" → Overfitting. Your fixes: more data, regularization (dropout, L2, early stopping), simpler model, augmentation, reduce training epochs.

**Other test:** "Train and val are both 62%." → Underfitting. Your fixes: bigger model, better features, less regularization, train longer, check for data leakage in the other direction (bad features).

### Overfitting

Model learns noise as if it were signal. Train performance great, test performance bad.

**Symptoms:** large train-val gap; loss curves diverge; performance degrades as you train longer.

**Fixes — know all of these:**
- **More data** — the single most effective fix when available
- **Regularization:**
  - **L2 (weight decay):** penalize large weights — `loss + λ·Σw²`. Standard default.
  - **L1 (lasso):** penalize absolute weights — `loss + λ·Σ|w|`. Encourages sparsity (feature selection side effect).
  - **Elastic Net:** combination of L1 + L2.
  - **Dropout:** randomly zero out activations during training (DNNs). Typical rate 0.1–0.5.
  - **Batch normalization / Layer normalization:** normalize activations; has a regularization side effect.
  - **Weight decay in optimizer:** AdamW's decoupled weight decay is the modern default.
- **Early stopping:** stop training when validation loss starts rising.
- **Data augmentation:** synthetic variants of training examples (images: crops/flips/rotations; text: back-translation; tabular: mixup).
- **Simpler model / fewer parameters.**
- **Ensembling** (averaging / bagging) reduces variance.

### Underfitting

Model too weak to capture the pattern. Train and val both poor.

**Fixes:** bigger model, richer features (crosses, polynomial, embeddings), lower regularization, longer training, better optimizer.

### Train / validation / test splits

- **Train:** fit the parameters.
- **Validation:** tune hyperparameters, pick the model, decide when to stop.
- **Test:** held out until the very end; reported once; do NOT tune on it.

**Temporal split for production ML:** train on earlier data, validate on later. Never shuffle randomly for time-dependent data — you'll leak the future.

**K-fold CV:** only for static/IID data. For time-series, use walk-forward CV (train on weeks 1–3, val on 4; then train on 1–4, val on 5; etc.).

### Loss functions (know when to use each)

- **Binary cross-entropy (log loss):** binary classification with probabilistic outputs. Standard for CTR, harmful content. Penalizes confidently wrong predictions sharply.
- **Categorical cross-entropy (softmax):** multi-class classification.
- **MSE (L2):** regression; penalizes outliers quadratically.
- **MAE (L1):** regression; robust to outliers.
- **Huber loss:** regression; L2 for small errors, L1 for large. Best of both.
- **Hinge loss:** SVM / max-margin classifiers.
- **Pairwise ranking losses** (BPR, RankNet): rank order matters — minimize pairs where a negative scores higher than a positive.
- **Listwise ranking losses** (LambdaRank, ListNet): optimize list-level ranking metrics directly (NDCG).
- **Contrastive loss / triplet loss / InfoNCE:** metric learning, embedding training; pull positives close, push negatives away. Used in two-tower models.
- **Focal loss:** for extreme imbalance; down-weights easy examples so the model focuses on hard ones. Used in object detection.

### Optimizers

- **SGD** with momentum: classic, often best final accuracy for images if tuned. Needs LR schedule.
- **Adam / AdamW:** adaptive learning rate per parameter, faster convergence, robust defaults. AdamW fixes weight decay coupling. **Modern default for DNNs.**
- **Adagrad / FTRL:** strong for sparse high-dim features (ads, recsys); handles sparse gradients well.
- **LR schedules:** warmup + cosine decay is the modern standard for big DNNs.

### Regularization vs normalization vs standardization (don't confuse)

- **Regularization** = techniques to prevent overfitting (L1/L2/dropout/early stopping).
- **Normalization / standardization** = feature preprocessing (z-score, min-max, log).
- **Batch/Layer normalization** = normalizing activations *inside* the network.

Saying "I'll add normalization to prevent overfitting" when you mean "L2 regularization" is a junior tell.

### Model families — tradeoff mental model

| Family | When it shines | When it doesn't |
|---|---|---|
| **Linear / Logistic regression** | Tabular, interpretable, tons of sparse features, CTR baseline | Can't learn non-linear interactions without manual feature crosses |
| **Decision tree / Random Forest** | Tabular, mixed types, interpretable-ish | Doesn't extrapolate; weaker than GBDT |
| **GBDT (XGBoost, LightGBM)** | Tabular — often #1 on Kaggle; strong baselines for CTR, fraud | Sparse high-card features (needs manual encoding); no GPU; hard to online-learn |
| **Deep NN (MLP)** | Large data, embeddings, learned feature interactions | Tabular with small data — GBDT often beats it |
| **CNN** | Images, some time-series | Not for unstructured tabular |
| **Transformer** | Text, sequences, increasingly images/audio | Compute-hungry; overkill for small tasks |
| **Two-tower / dual encoder** | Retrieval at scale (user ↔ item matching) | Can't model user × item feature crosses |
| **Graph NN (GNN)** | Relational data with structure (social graph, molecules) | Training at graph-scale is hard; infra-heavy |
| **Collaborative filtering / MF** | Rec systems with lots of interactions | Cold start (new users/items); no content features |

### Task types — which model do you reach for first?

The previous table reads family → task. This one reads the reverse — task → default model. In an interview, when you've just decided your ML objective ("this is a binary classification problem on tabular data with 100M rows"), you should be able to name your go-to and your backup within 5 seconds.

Every entry has: the task type, what a typical instance looks like, the go-to baseline, the go-to production model, and a note on when to deviate.

**Binary classification**
- *Examples:* CTR prediction, harmful content flagging, fraud, spam, churn
- *Baseline:* logistic regression with hand-crafted features + L2
- *Production default (tabular):* GBDT (XGBoost / LightGBM) for small–medium, Wide & Deep / DCN-v2 / DeepFM when you have huge embedding tables and massive data
- *Production default (text):* fine-tuned BERT-family → classifier head
- *Production default (image):* ViT or ResNet backbone → classifier head
- *Loss:* binary cross-entropy
- *Key metric:* AUC (balanced) or PR-AUC (imbalanced); log-loss if probabilities matter
- *Gotcha:* class imbalance is the #1 trap (see focal loss, downsampling + recalibration)

**Multi-class classification**
- *Examples:* topic classification, intent classification, image labeling into N categories
- *Baseline:* softmax logistic regression or one-vs-rest binary
- *Production default:* DNN with softmax head; for text/image use pre-trained encoder + head
- *Loss:* categorical cross-entropy
- *Key metric:* top-1 / top-k accuracy, macro-F1 (if classes imbalanced)
- *Gotcha:* confusing classes — use confusion matrix in error analysis

**Multi-label classification (not the same as multi-class)**
- *Examples:* "does this post contain: [violence, nudity, hate speech, spam]?" — can be multiple
- *Baseline:* one binary classifier per label
- *Production default:* shared-encoder DNN with N sigmoid heads (one per label); multi-task if labels correlate
- *Loss:* sum of binary cross-entropies
- *Gotcha:* label correlations (violence and hate speech co-occur) — multi-task helps

**Regression**
- *Examples:* ETA prediction, price prediction, demand forecasting, rating prediction
- *Baseline:* linear regression; for time-series, ARIMA or exponential smoothing
- *Production default (tabular):* GBDT (still dominant); DNN when you have embeddings/sequences
- *Production default (quantile / calibrated intervals):* LightGBM quantile regression or DNN with pinball loss
- *Loss:* MSE (clean data), MAE (outliers), Huber (balanced), pinball (quantiles)
- *Key metric:* MAE, RMSE, MAPE (percentage), plus calibration if you serve uncertainty
- *Gotcha:* outliers destroy MSE training; heteroscedasticity — error variance depends on input

**Ranking (learning to rank)**
- *Examples:* search results, feed ranking, ads, product recommendations
- *Baseline:* pointwise — train a regressor/classifier on per-item relevance, sort by score
- *Production default:* pointwise multi-task DNN (Meta Feed/Reels style) — simpler to train, calibrates naturally
- *More sophisticated:* pairwise (RankNet, BPR) or listwise (LambdaRank, LambdaMART, ListNet) — optimize rank-sensitive loss; LambdaMART on GBDT is classic
- *Key metric:* NDCG@k, MAP, MRR, Recall@k
- *Gotcha:* position bias in training labels; offline metric ≠ online engagement

**Retrieval (nearest neighbor over huge catalog)**
- *Examples:* candidate generation for recs, semantic search, image search, PYMK seed
- *Baseline:* collaborative filtering (matrix factorization) or BM25 lexical for text
- *Production default:* two-tower / dual-encoder DNN, item embeddings indexed in ANN (HNSW/FAISS/ScaNN)
- *Loss:* contrastive / InfoNCE / triplet — pull positives close, push negatives far
- *Key metric:* Recall@k on held-out engagement
- *Gotcha:* hard negative mining; catalog drift (embeddings age)

**Recommendation (as a composite problem)**
- *Examples:* Reels, Feed, YouTube home, Netflix, Amazon
- *Architecture:* two-stage — two-tower retrieval → multi-task MMoE ranker
- *This is a *design*, not a model choice — see Phase 4 and Case Study 1

**Sequence / session modeling**
- *Examples:* next-item prediction, session-based recs, user behavior modeling
- *Baseline:* most-recent-item, Markov chain, RNN (GRU4Rec)
- *Production default:* transformer-based (SASRec, BST, Meta's HSTU); attention over history
- *Loss:* usually cross-entropy over next item vocabulary, or contrastive
- *Gotcha:* sequence length vs compute; cold-start short sequences

**NLP tasks**
- *Text classification:* fine-tuned BERT-family + classifier head; for massive scale or cost, distilled models (DistilBERT, TinyBERT)
- *Named entity / token classification:* BERT + token classification head + CRF layer
- *Text generation / summarization:* decoder-only LLM (GPT-family) or encoder-decoder (T5); for production retrieval-augmented generation (RAG) is common
- *Semantic similarity:* sentence-transformers (dual-encoder BERT trained with contrastive loss)
- *Translation:* encoder-decoder transformer
- *Gotcha:* pre-trained backbone size vs latency; domain adaptation for specialized text

**Computer vision tasks**
- *Image classification:* ResNet (classical), ViT (modern); pre-trained on ImageNet then fine-tune
- *Object detection:* YOLO (fast, single-stage), Faster R-CNN (accurate, two-stage), DETR (transformer-based)
- *Segmentation:* U-Net (medical, simple), Mask R-CNN (instance), SAM-family (foundation)
- *Image embedding (for retrieval):* CLIP — learns joint text-image embeddings; strong zero-shot
- *Gotcha:* inference cost on video (frame sampling matters)

**Graph tasks**
- *Node classification:* GraphSAGE, GCN, GAT; or tabular features + GBDT as baseline
- *Link prediction (PYMK):* GraphSAGE + dot product / MLP; or handcrafted graph features (common neighbors, Adamic-Adar) + GBDT baseline
- *Graph-level prediction:* pool node embeddings → classifier
- *Gotcha:* scale (billions of nodes needs careful sampling); embedding staleness

**Anomaly / outlier detection**
- *Examples:* fraud, bot detection, intrusion, manufacturing defects
- *Unsupervised baseline:* Isolation Forest, Local Outlier Factor, one-class SVM
- *Supervised when labels exist:* heavily imbalanced binary classification — focal loss, oversampling
- *Hybrid:* autoencoder reconstruction error + supervised classifier ensemble
- *Gotcha:* extreme class imbalance; adversarial — attackers adapt; drift

**Time series forecasting**
- *Classical:* ARIMA, exponential smoothing, Prophet
- *Modern tabular:* LightGBM with lag features + rolling aggregates (often wins in practice)
- *Deep:* DeepAR, Temporal Fusion Transformer, N-BEATS
- *Gotcha:* non-stationarity; seasonality detection; cold-start new series

**Clustering / unsupervised grouping**
- *Examples:* user segmentation, topic discovery
- *Baseline:* k-means, hierarchical clustering
- *Modern:* embed with a pre-trained encoder → cluster in embedding space (HDBSCAN is good)
- *Gotcha:* choosing k; evaluation is subjective

**Reinforcement learning / bandits**
- *Examples:* online ad bidding, dynamic pricing, exploration in recs
- *Simpler:* contextual multi-armed bandit (LinUCB, Thompson sampling) — often sufficient
- *Full RL:* policy gradient (PPO), DQN — rare in production recs but used in some ads systems
- *Gotcha:* exploration vs exploitation balance; off-policy evaluation is hard

### How to use this in an interview

**The flow:** after you frame the task in Phase 1c ("this is a ranking problem with multi-task labels"), in Phase 4 you should immediately be able to say:

> *"Given this is multi-task ranking, my baseline is pointwise logistic regression on hand-crafted features. For production I'd propose a multi-task DNN — specifically MMoE — trained on per-item pointwise losses per task. If the catalog were smaller I might use GBDT + LambdaMART instead, but MMoE handles the embedding tables and shared representation better for billions of items."*

That sentence = framing + baseline + production model + alternative + reason — the entire Phase 4a–4c expressed as one confident statement. Getting fluent at this is worth more than memorizing any specific architecture.

### Other foundational terms to be fluent in

- **Supervised / unsupervised / semi-supervised / self-supervised:** already covered in Phase 3.
- **Gradient descent / backprop:** know at intuition level. "Compute loss, get gradients via chain rule, update weights opposite the gradient."
- **Vanishing / exploding gradients:** old problem in deep networks. Fixes: ReLU activations, batch norm, residual connections, careful init (Xavier/He), gradient clipping.
- **Activation functions:** ReLU (default), GELU (transformers), sigmoid (binary output), softmax (multi-class output), tanh (rarely now).
- **Attention:** weighted average over a set, where weights depend on a query. Core of transformers, DIN/DIEN, modern sequence recs.
- **Embedding:** dense learned vector representing a discrete item (ID, word, image). Similarity (cosine / dot) is meaningful.
- **Parametric vs non-parametric:** parametric has fixed params (LR, DNN); non-parametric grows with data (kNN, ANN, tree-based to an extent).
- **Generative vs discriminative:** generative models P(x, y) or P(x | y); discriminative models P(y | x). For classification, discriminative is usually stronger (logistic regression, DNN).
- **Precision vs recall:** precision = of what I flagged, how much was right; recall = of what was actually positive, how much did I catch. Tradeoff controlled by threshold.
- **F1 = harmonic mean of precision and recall.** Good for imbalanced when you want a single number.

### When the interviewer probes ML basics

Short, direct answers beat rambling. Examples of good-short:

- *"What's L2 regularization?"* → "Adds `λ·Σw²` to the loss. Penalizes large weights, shrinks them toward zero, reduces overfitting. Hyperparameter λ tunes strength."
- *"Why does dropout work?"* → "Randomly zeros activations during training, forces the network to not rely on any single neuron, acts like an ensemble of sub-networks, reduces co-adaptation. Turned off at inference."
- *"When do you use L1 vs L2?"* → "L1 for sparsity / feature selection (zeroes weights out); L2 for general shrinkage (weights stay small but non-zero). Elastic Net combines both when you want both properties."

---

## Phase 1 — Framing (5–7 min)

Three sub-steps, in this order:

### 1a. Clarify

Ask until you have confident answers for:

- **Who are the users?** (new vs returning, creators vs consumers, geo)
- **What surface?** (feed, sidebar, notification, search page)
- **Scale?** DAU, QPS of requests, size of item catalog
- **Latency budget?** For online ranking, usually 100–500 ms end-to-end. Feed loads aim for p99 under ~500 ms.
- **Real-time or batch inference?**
- **Is there a current system?** (almost always yes — you're replacing or augmenting)
- **Any hard constraints?** Privacy (on-device?), fairness, regulatory

Don't fire all ten questions. Ask 3–4 high-signal ones, get answers, ask follow-ups.

### 1b. Business objective

Write it on the board. Examples:

- "Maximize Reels watch time while keeping complaint rate flat"
- "Reduce exposure to harmful content among users who see it"
- "Maximize revenue per ad impression, conditional on user relevance"

The business objective should name the **guardrail**. Raw CTR isn't a business objective — it invites clickbait.

### 1c. ML objective

Translate. This is where you get senior points if you pick the right framing:

- **Ranking** (reels, feed, ads, search) — most common
- **Retrieval / candidate generation** — upstream of ranking
- **Classification** (harmful content, bot detection, CTR prediction)
- **Regression** (ETA, price, watch-time prediction)
- **Embedding learning** (user/item reps, search)
- **Sequence modeling** (next-item prediction, sessions)

Then **name the label**:

- Explicit: like, share, follow, rating
- Implicit: click, watch, dwell time, skip
- Derived: watch > 10s as "engagement positive"; skipped within 3s as "hard negative"

Always flag: "The naive label is click, but that's a poor proxy for satisfaction because of clickbait, so I'd propose watch-time > threshold as the primary label, with additional heads for likes/shares."

That sentence alone = senior signal.

---

## Phase 2 — High-level sketch (2–3 min)

Don't perfect this. One pass. Typical ML ranking system looks like:

```
         ┌──────────────────────────────────────────────────┐
Client → │  Request router / edge                           │
         └────┬─────────────────────────────────────────────┘
              │
              ▼
  ┌──────────────────────┐     ┌────────────────────┐
  │ Candidate Generation │←────│ Offline indexes    │
  │ (multiple sources,   │     │ (ANN, inverted,    │
  │  fan-in, ~thousands) │     │  popularity, etc.) │
  └──────────┬───────────┘     └────────────────────┘
             │
             ▼
  ┌──────────────────────┐     ┌────────────────────┐
  │ Feature Hydration    │←────│ Feature Store      │
  │ (user, item, context)│     │ (online + offline) │
  └──────────┬───────────┘     └────────────────────┘
             │
             ▼
  ┌──────────────────────┐
  │ Ranking (heavier     │
  │  model, ~hundreds)   │
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │ Re-ranking / policy  │  ← diversity, freshness, business rules,
  │ (filters, blending)  │    exploration, ad insertion
  └──────────┬───────────┘
             ▼
           Result

                           ┌─────────────────────┐
                           │ Logging / Eventing  │ → training data loop
                           └─────────────────────┘
```

**The two-stage (or multi-stage) retrieval + ranking pattern is the single most important architecture in ML system design.** It shows up in Reels, Feed, Search, Ads, People-You-May-Know, Shopping. Internalize it.

**Why two stages?**
- Catalog has millions–billions of items. Can't run a heavy model on all of them.
- Stage 1 (retrieval/candidate-gen) is cheap per item, recalls ~thousands from billions.
- Stage 2 (ranking) is expensive per item but only runs on ~thousands.
- Sometimes a third stage (re-ranking) for diversity, freshness, policy rules.

---

## Phase 3 — Data & Features (~10 min, high priority)

### 3a. Training data

Say out loud:

- **Where does it come from?** Logged user interactions, typically. Mention the pipeline: client emits events → stream (Kafka) → offline store (data warehouse) → training dataset.
- **How do you label?** Usually implicit feedback. Acknowledge the problems:
  - **Missing negatives:** a non-click isn't definitely "disliked" — the user may not have seen it. You need impression logs (which items the user saw) to construct true negatives.
  - **Position bias:** items at the top get more clicks regardless of quality. Address via position-aware features or debias at training time (see Phase 6 deep dives).
  - **Selection bias:** your training data comes from items your *current* model selected. This creates a feedback loop. Address via exploration / random slots.
- **Label leakage:** don't use features that contain info about the future. Always split temporally, never randomly.
- **Data buckets** — a senior candidate mentions all three:
  - **Supervised:** labeled interactions
  - **Semi-supervised:** weak labels, pseudo-labels from current model
  - **Self-supervised / unsupervised:** pre-training embeddings on clicks/co-views without explicit labels
- **Class imbalance:** CTR is often 1–5%. Downsample negatives for training, re-weight or re-calibrate at serving.

### 3b. Features

Don't dump. Pick 5–10 with a hypothesis for each. Organize by source:

**User features:**
- Static: demographics, account age, device, language, country
- Historical behavior: top categories watched, engagement rate, sessions/day
- Embeddings: learned from past interactions (dense user embedding)

**Item features:**
- Content: for video — visual embedding (from pre-trained encoder), audio embedding, text/caption embedding; for posts — text embedding, image/video embedding
- Metadata: creator, upload time, language, category, length
- Engagement aggregates: CTR last 24h, like rate, completion rate, diversity of audience

**Context features:**
- Time (hour, day of week), timezone, location
- Device, network quality, session position (1st item vs 20th)
- Query (for search)
- Recent session items (what this user just watched — short-term interest)

**Interaction features (user × item):**
- Past count of views by this user of this creator
- Similarity (user embedding • item embedding)
- Whether the user follows the creator

**Feature freshness matters:**
- **Batch features** (updated hourly/daily): user long-term profile, item aggregate stats — computed offline, served from a feature store
- **Near-real-time features** (minutes): trending items, short-term session features — updated via streaming
- **Real-time features** (per-request): the last 10 items in this session, current device — computed at request time

Mentioning this hierarchy proactively is senior signal.

### 3b-2. From raw signals to engineered features (Meta calls this out explicitly)

Meta's career page names this skill directly: *"'number of likes' can be a good feature suggestion, but a better feature might also involve normalization, smoothing, and bucketing."* Practice taking any raw signal and transforming it into something a model can actually use well.

**The mental drill:** for every feature you propose, also say what transformation you'd apply and why. This is the difference between a feature dump (junior) and feature engineering (senior).

**The pattern playbook — apply these to any raw signal:**

**1. Normalize by a denominator to remove scale confounds.**
- Raw: `num_likes` (a creator with 100M followers always wins)
- Better: `like_rate = likes / impressions` (engagement intensity)
- Even better: `like_rate_z_score_within_category` (is this post engaging *for its category*?)

**2. Log-transform long-tailed distributions.**
- Raw: `view_count` (ranges from 0 to 100M, power-law distributed)
- Better: `log1p(view_count)` — compresses the tail, lets linear models use it
- DNNs handle this better but still benefit; tree models largely don't care

**3. Smooth low-sample estimates.**
- Raw: `item_ctr = clicks / impressions` (an item with 1 impression and 1 click has CTR=1.0, which is garbage)
- Better: **Bayesian smoothing / shrinkage** — `smoothed_ctr = (clicks + α·prior_ctr) / (impressions + α)`. Shrinks toward a prior (global CTR, category CTR) when sample size is low. Classic technique.
- Even better: **Empirical Bayes** — estimate the prior from the data distribution.

**4. Bucket / discretize continuous values.**
- Raw: `user_age = 23.7` (continuous)
- Better: bucket into `[<18, 18-24, 25-34, 35-44, 45-54, 55-64, 65+]` and embed each bucket
- Why: linear models can't capture non-monotonic relationships (engagement might be U-shaped in age); bucketing + embedding handles it. Also robustifies against age being entered as 130 or -5.
- **Quantile buckets** (deciles) are safer than uniform buckets for skewed features.

**5. Time-window aggregates at multiple scales.**
- Raw: "has this user seen this creator before?" (binary)
- Better: counts at multiple windows — `views_last_1h`, `views_last_24h`, `views_last_7d`, `views_last_30d`. The ratio `views_last_24h / views_last_30d` tells you if interest is rising or declining.
- Multi-scale windows let the model learn whatever time-scale matters.

**6. Recency decay.**
- Raw: "did the user interact with this category?" (ignores when)
- Better: `Σ exp(−Δt / τ)` over past interactions, with half-life τ chosen per use case (τ = 1 hour for session intent, τ = 7 days for long-term preference).
- Captures "recent activity weighs more."

**7. Cross features (interaction features).**
- Raw: `user_country`, `item_language`
- Better: `is_language_match = (user_primary_language == item_language)`, `user_country × item_creator_country` cross
- Rationale: DNNs can learn some of these but explicit crosses help (especially for sparse linear/wide components). This is literally what the "Wide" in Wide & Deep is for.

**8. Embeddings for high-cardinality categorical.**
- Raw: `user_id` (billions of distinct values)
- Better: learned user embedding (dense vector). Table sharded across machines, or hashed if cardinality is too high.
- Raw: `creator_id`, `hashtag_id`, `device_model` — all embeddings.

**9. Target encoding (careful).**
- Raw: `zip_code` (high cardinality)
- Better: replace zip with `mean(target | zip)` (avg CTR for that zip code)
- ⚠️ **Leakage risk:** if you compute the encoding on the same data you train on, you've leaked the label. Fix: out-of-fold encoding (compute on held-out folds) or use only historical data (strictly before the train example's timestamp).

**10. Handle missing values deliberately.**
- Options: impute with mean / median / mode; add a "was_missing" indicator column (missingness itself may be informative); use a learned "missing" embedding for categoricals; let tree models handle NaN natively (LightGBM/XGBoost do).
- Don't just drop rows — you lose signal and may introduce selection bias.

**11. Handle outliers.**
- Cap / clip to percentiles (e.g., clip values above 99th percentile)
- Log transform (see above)
- Robust scaling (use median + IQR instead of mean + stddev)

**The full worked example — "number of likes" → a production feature:**

Bad: `num_likes` (raw)
Better: `like_rate = likes / impressions`
Better: `log1p(like_rate)` to handle skew
Better: `smoothed_like_rate` with Bayesian prior (so items with 2 impressions don't dominate)
Better: `like_rate_normalized_within_category` (engagement relative to peers)
Better: all of the above computed over multiple time windows (last 1h, 24h, 7d) to capture trajectory
Best: plus a `like_rate_rank_percentile` (is this in top 10% of similar items right now)

That's the progression from "junior feature" to "senior feature." Say the first, then say "and I'd improve it by [the progression]."

**Interview habit:** when an interviewer asks "what feature would you use?", answer with the **transformed** version, not the raw one. "I'd use a smoothed, log-transformed like rate, normalized within content category, computed over 1h and 24h windows to capture both spike and sustained engagement."

### 3c. Encodings

- **Numerical:** standardize (z-score) or log-transform for long-tail (view counts)
- **Categorical:**
  - Low cardinality → one-hot
  - High cardinality (user_id, item_id) → learned embeddings
  - Ultra-high cardinality → hashing trick + embedding
- **Text:** pre-trained transformer embeddings (BERT-family); for scale, distilled versions
- **Images/Video:** pre-trained visual backbone (ViT, ResNet, CLIP) → embedding
- **Missing values:** impute with mean/median/mode, or use a learned "missing" embedding

### 3d. Feature store (1 sentence is enough)

"I'd use a feature store (e.g. something like FBLearner Feature Store internally, or Feast / Tecton externally) to serve features with a consistent schema across training and serving — avoiding train-serve skew is critical."

---

## Phase 4 — Modeling (~10 min, high priority)

### 4a. Baseline

Always. Mention one:
- **Popularity-based:** top N by global or segmented popularity
- **Rule-based:** recency + creator follows
- **Collaborative filtering** (matrix factorization, implicit-feedback): classic for recs
- **Logistic regression on hand-crafted features:** still a strong CTR baseline

Why baselines matter: "Without a simple baseline, I can't quantify the value of complexity I add."

### 4b. Candidate generation (if two-stage)

Several approaches running in parallel, outputs unioned:

- **Collaborative filtering / matrix factorization** — classic, fast
- **Two-tower neural network:** user tower + item tower → dot-product similarity; item embeddings stored in an ANN index (FAISS / HNSW / ScaNN). At request time, user tower runs, ANN retrieves top K.
- **Graph-based:** random walks on user-item graph (e.g. PinSage style)
- **Heuristic channels:** trending, recently uploaded, followed-creator content, locality
- **Personalized + non-personalized mixed:** for new users (cold start), weight non-personalized higher

Key numbers: stage 1 retrieves ~1000–10000 candidates from billions in tens of ms.

### 4c. Ranking model

This is usually where the interview goes deep. Options:

- **GBDT (XGBoost, LightGBM):** strong tabular baseline, interpretable, no GPU needed. Still used in production at many places.
- **Deep learning ranking models:**
  - **Wide & Deep** (2016): memorization (wide linear part) + generalization (deep part)
  - **Deep & Cross (DCN, DCN-v2):** learns feature crosses explicitly
  - **DeepFM:** factorization machines + DNN
  - **DIN / DIEN (deep interest network):** attention over user history items
  - **Transformer-based sequence models:** for session / history modeling (BST, SASRec, Meta's HSTU more recently)
- **Multi-task learning:** single model predicts multiple heads (click, watch, like, share, skip). **This is the Meta default for Feed and Reels ranking.** You average the losses (weighted), and at serving you combine the head predictions via a formula that encodes the business objective. E.g., `score = w1 * P(watch_long) + w2 * P(like) + w3 * P(share) − w4 * P(skip)`.
- **MMoE (Multi-gate Mixture of Experts):** handles task conflict in multi-task learning. Classic in YouTube / Meta ranking.

Pick ONE to go deep on and defend.

### 4d. Architecture detail

For your chosen model, describe:

- **Input layer:** how the features come in (continuous → normalization, categorical → embedding lookup, sparse → hashing)
- **Feature interactions:** DCN cross layers? Attention? FM?
- **Shared layers / expert networks** (if MMoE)
- **Task-specific heads** (if multi-task) — each is usually a few fully-connected layers ending in sigmoid
- **Loss:** binary cross-entropy for classification heads; weighted sum across tasks; calibration if needed
- **Regularization:** dropout, L2, label smoothing
- **Training:** optimizer (Adam / Adagrad — Adagrad is common in recsys for sparse features), learning rate schedule, batch size

Be ready for "how many parameters?" — acceptable to say "on the order of tens of millions to low hundreds of millions for the main ranking model; item embedding tables can dominate."

### 4e. Training setup

- **Offline training:** batch jobs, daily or weekly retrains
- **Online learning / incremental:** for fast-moving distributions (ads, trending). Hourly updates, or streaming SGD on logged events
- **Warm-start** from previous checkpoint
- **Distributed training:** data-parallel on GPUs; for huge embedding tables, model-parallel (parameter server or sharded embeddings)

One sentence on each is enough unless the interviewer probes.

### 4f. Model risks & how to mitigate them

Meta explicitly calls this out: *"Can you anticipate risks and how do you mitigate those risks?"* After picking your model, proactively name 3–4 risks and the mitigations. This is a core senior signal — it shows you've deployed models before, not just read about them.

**The checklist (organized by cause):**

**Data risks:**
- **Leakage** — a feature contains future info → validate with a feature-by-feature "is this available at prediction time?" audit; temporal splits
- **Distribution shift between train and serve** → monitor feature distributions; retrain cadence
- **Label noise** — implicit labels are noisy (a skip might be a bathroom break) → smoothing, multi-signal labels, robustness via noise-tolerant losses
- **Imbalanced classes** → downsampling + recalibration, class weights, focal loss
- **Selection bias** — training data only includes what your current model chose → exploration, IPS weighting
- **Not enough data for tail segments** (new users, new languages) → data augmentation, transfer learning, hierarchical models that share across segments

**Modeling risks:**
- **Overfitting** → L2, dropout, early stopping, more data, simpler model
- **Underfitting** → bigger model, better features, less regularization
- **Miscalibrated probabilities** → Platt / isotonic post-hoc calibration
- **Task conflict in multi-task** → MMoE, task-specific heads, tuned loss weights
- **Hyperparameter sensitivity** → Bayesian HP search, seed-sensitivity checks

**Production risks:**
- **Training-serving skew** — features computed differently → feature store with shared library
- **Latency / cost blowup** → distillation, quantization, caching, smaller model
- **Feedback loop / echo chamber** → exploration budget, off-policy correction
- **Cold start** (new user, new item) → fallbacks, content embeddings, onboarding signals
- **Staleness** — model degrades between retrains → regular retraining, drift monitoring, online learning for fast-moving
- **Concept drift** — underlying relationship changes (covid changed everyone's behavior) → monitor target metric; retrain on recent data more heavily
- **Cascading failure** — upstream service down → graceful degradation (fall back to popularity, cached results)
- **Adversarial gaming** — creators/spammers optimize for your metric → integrity layer, diverse signals, engagement-bait classifiers

**Business/ethics risks:**
- **Clickbait / rage-bait optimization** — if your target is CTR alone, bad content wins → richer labels (watch time, explicit feedback), guardrail metrics
- **Filter bubbles / lack of diversity** → MMR re-ranker, exploration, diversity constraint in objective
- **Fairness / disparate impact** → measure outcomes per protected group; debiasing techniques if regressions appear
- **Privacy** — leaking training data via embeddings or outputs → differential privacy, on-device inference where appropriate

**How to say this in an interview:** don't recite the full list. Pick 3–4 most relevant to your specific system and say them proactively. E.g. for Reels ranking:

> *"A few risks I'd call out: first, selection bias — we only see engagement on items the current ranker picked, so I'd reserve an exploration budget. Second, clickbait — if we only target clicks or short watch time, rage-bait wins, so I'm using `P(watch > 10s)` plus a skip penalty and a complaint guardrail. Third, position bias — I'd include slot index as a training feature and drop it at serve time. Fourth, cold start for new items — content embeddings and seeded exposure in an exploration channel."*

That's four risks, each with a mitigation, in ~30 seconds. Senior signal.

---

## Phase 5 — Inference & Evaluation (~7 min)

### 5a. Serving

- **Model serving:** a model server (like TorchServe, TF Serving, internally at Meta: PyTorch-based custom stack) behind the ranking service
- **Feature hydration:** ranking service fetches features for (user, items) from feature store — this is a large fanout and often the bottleneck
- **Latency budget:** typically 50–200 ms for the ranking model itself. Total page latency often <500 ms p99.
- **Caching:** cache candidate lists per-user for a short TTL (seconds to minutes) if traffic is high and re-ranking frequency allows
- **Batching:** stack many (user, item) pairs into a single inference call to amortize overhead
- **Optimizations:**
  - **Quantization** (fp16, int8) for inference speedup
  - **Distillation** — train a smaller student model from a large teacher; common when you want low-latency serving of a heavy model
  - **Pruning** — remove low-weight connections
  - **Embedding table sharding** — the embedding tables for user/item IDs can be hundreds of GB, sharded across machines
  - **ANN index compression** (product quantization) for candidate retrieval

### 5b. Offline evaluation

Depends on task:

- **Classification:** AUC, PR-AUC (especially for imbalanced), log loss, calibration (ECE)
- **Ranking:** NDCG@k, MAP, MRR, Recall@k, Hit@k
- **Regression:** RMSE, MAE
- **Counterfactual / replay evaluation:** simulate the new ranker on logged impressions to estimate lift without going live

**Temporal split only.** Train on week 1–3, validate on week 4. Random splits leak future info.

**Held-out users vs held-out interactions** — prefer leave-one-interaction-out for user-cold-start estimation; leave-one-user-out for true cold start.

### 5c. Online evaluation

- **A/B testing** is the gold standard. Split users (or sessions) into control and treatment.
- **Metrics to track:**
  - **Primary:** the business objective (watch time, revenue)
  - **Guardrails:** complaints, unfollows, session length, retention (7-day, 28-day)
  - **Operational:** p50/p99 latency, error rate, inference cost
- **Duration:** long enough to capture long-term effects. A week is minimum; a month is common for retention signals.
- **Novelty effects:** new things get a bump just because they're new. Don't declare victory early.
- **Interleaving:** alternate rankers' results within a single session — much more sensitive than A/B because it removes between-user variance. Good for fast iteration on ranker quality.
- **Shadow mode:** run the new model in production but don't use its output. Validates latency and correctness without user impact.

### 5d. Monitoring in production

- **Model metrics:** prediction distribution shift (are outputs drifting from expected distribution?), calibration
- **Data metrics:** feature distribution drift per feature, null rates, latency of features
- **Business metrics:** live dashboards on CTR, watch time, revenue — compared to baselines
- **Retraining cadence:** scheduled (daily/weekly) + triggered (on drift detection)
- **Rollback:** fast rollback on regression — be ready to answer "how fast?"

### 5e. Model debugging — the "it's not working, now what?" playbook

Meta's career page specifically says: *"What will you do after you train the model and the model doesn't perform well? How do you go about debugging an ML model?"* This comes up a lot. Have a structured answer.

**The diagnostic ladder — work top to bottom:**

**Step 1 — Is it actually bad? Check the baseline.**
- Are you comparing against a real baseline (previous model, heuristic, popularity) or thin air?
- Is the metric right? Does offline improvement translate to online? If offline good but online bad → train-serve skew or wrong metric.

**Step 2 — Look at the loss curves.**
| Pattern | Diagnosis | Fix |
|---|---|---|
| Train and val both high, flat | **Underfitting** | Bigger model, better features, lower regularization, longer training, better optimizer |
| Train goes down, val goes up | **Overfitting** | More data, regularization (L2/dropout), early stopping, augmentation |
| Train and val both NaN/diverge | **Training instability** | Lower LR, gradient clipping, better init, check for bad inputs |
| Train loss jumps around | **LR too high or bad data** | Lower LR, shuffle data, check batch composition |
| Val loss erratic | **Val set too small, noisy labels** | Bigger val set, cross-validation |
| Both metrics fine but predictions are one-class | **Class collapse** | Class imbalance → weighted loss or resampling |

**Step 3 — Data sanity checks (do these BEFORE touching the model).**
- Visualize the label distribution — is it what you expect?
- Plot feature distributions in train vs val vs test — are they the same?
- Check for **leakage** — is any feature suspiciously predictive (AUC 0.99)? Drop it and retrain; if score drops to normal, it was leaky.
- Check label quality — spot-check 100 examples by hand. Are the labels what you think they are?
- Check for duplicates between train and val (can inflate val metrics dramatically)
- Check for class imbalance mismatch — train might be downsampled but val might be natural distribution

**Step 4 — Error analysis (where is the model wrong?)**
- Slice performance by segment: user cohort, item category, country, device, new vs returning users
- A model with 85% overall accuracy might be 95% on power users and 50% on new users — very different problem than uniform 85%
- Look at top-loss examples: which predictions is the model most wrong about? Is there a pattern?
- Confusion matrix (classification): which classes get mixed up?
- Residual plots (regression): is error correlated with any input feature?

**Step 5 — Model capacity questions.**
- Train on a small sample (1000 examples) — can the model overfit it to ~0 loss? If **no** → architecture bug (loss wrong, gradient not flowing, frozen weights). If **yes** but full training underfits → you need more capacity or better features.
- This "overfit a batch" test is one of the most useful debugging tools and worth mentioning in interviews.

**Step 6 — Feature diagnostics.**
- **Feature importance** (permutation importance, SHAP, or tree-based importance): which features are driving predictions? Are they the ones you expected?
- **Feature ablation:** remove one feature group at a time, retrain, measure drop. Big drop = important feature group.
- **Leakage audit:** features whose importance is implausibly high
- **Null / missing rate check:** is a feature mostly null at serving time (present in training but not at serve)? That's train-serve skew.

**Step 7 — Training-serving skew (the silent killer).**
- Log the exact features used at serving time; replay them through training-time feature code; they should be identical.
- Compare prediction distributions offline (on held-out data) vs online (on live traffic) — if they diverge, you have skew.
- Typical culprits: different feature definitions, different aggregation windows, different null handling, different preprocessing.
- **This is where most "great offline, bad online" stories end.**

**Step 8 — If online performance is bad but offline is good.**
- **Distribution shift:** your held-out set is stale; live traffic is different. Check feature distributions live vs train.
- **Feedback loop:** the old model's biases are in your training data; new model inherits them.
- **Novelty / exploration:** users respond differently when the model behaves differently.
- **Calibration:** predicted probabilities are off — ranking can still be correct but downstream decisions (thresholds, auctions) break.
- **Latency:** the new model is slower; timeouts are dropping it; in production you measure "what actually returned."

**Step 9 — If live metrics regress after deployment.**
- Roll back first, diagnose second. Don't debug live.
- Compare treatment vs control on every segment, not just overall. A model can improve overall by hurting one segment a lot and helping another a little.
- Check guardrails first — was the regression primary or guardrail?
- Look for confounds: deployed during a holiday, concurrent experiment, infra incident

**How to say this in an interview — don't recite the whole list. Answer framework:**

*"First I'd check whether the problem is at data, model, or serving layer. I'd start by looking at loss curves to diagnose over/underfitting. Then I'd slice performance by segment — often the overall number hides that the model's terrible on a specific cohort. I'd also do an error analysis on the top-loss examples, and an 'overfit-a-batch' sanity check to make sure training is actually working. If offline looked good but online didn't, the first thing I'd suspect is train-serve skew in feature computation, and I'd log features at both ends to compare."*

That's a complete answer in 30 seconds. Have this memorized.

---

## Phase 6 — Deep Dives (interviewer-driven)

Things they'll likely probe. Have an opinion on each:

### Cold start
- **New user:** fall back to popularity / demographic segment / onboarding quiz; increase exploration (epsilon-greedy)
- **New item:** use content features (image/text embeddings) only; seed with uniform exposure for a short period; use content-based similarity to existing items

### Position bias
- In logged data, higher-positioned items got more clicks regardless of quality.
- Fix: include position as a feature at training (so the model learns "position effect"), then at serving drop it or set to a fixed value. Known as **position debiasing**.

### Popularity bias / rich-get-richer
- Popular items keep getting recommended, new items can't break in.
- Fix: explicit exploration budget, diversity constraints in re-ranker, content-based boosts for new items.

### Filter bubbles / diversity
- Re-ranking step: enforce diversity on creator, topic, format. MMR (maximal marginal relevance), determinantal point processes (DPPs), or simple rules.

### Feedback loops
- Your model's recommendations become the data you train on next → reinforcement of its own biases.
- Fix: exploration (random slots, epsilon-greedy, Thompson sampling), counterfactual training, off-policy correction.

### Calibration
- For ads/bidding, raw predicted P(click) must match actual click rate. Models often over-predict for rare events. Techniques: Platt scaling, isotonic regression post-training.

### Adversarial / integrity
- Spam, bots, gaming the recommender. Needs a separate integrity classifier upstream and a feedback system for flagged content.

### Drift
- Distribution of users, items, context all shift. Monitor feature distributions; retrain regularly; for rapid drift (ads, news), online learning.

### Fairness
- Ensure the model doesn't systematically advantage/disadvantage protected groups. Usually handled by product/policy teams but mentioning it = senior signal.

### Cost
- Ranking at scale costs millions in GPU. Mention: smaller student models via distillation, early exit networks, caching frequent features, int8 quantization.

---

# Part 2 — Case Studies

Three canonical Meta problems walked end-to-end. Memorize the structure of one, then you can adapt it to any problem.

## Case Study 1 — Video Recommendation (Instagram Reels / TikTok / YouTube Shorts)

This is THE most common Meta ML system design question. Expect it for Feed, Reels, Explore.

### Framing

**Clarify:**
- Surface: infinite vertical-scroll feed, autoplay, short-form (<60s)
- Scale: assume 2B DAU, 100+ reels/user/session, 100M+ items in catalog
- Latency: ~300 ms for generating next batch of reels
- Current system: assume there's an existing one we're replacing/augmenting

**Business objective:** Maximize quality-adjusted watch time per session, with guardrails on complaint rate, unfollows, and creator diversity.

- Why not raw watch time? Clickbait / rage-bait content wins.
- "Quality-adjusted" = bake in likes, shares, and skip-rate as signals.

**ML objective:** Multi-task ranking. Given (user, candidate items, context), predict:
- `P(watch > 10s)` — primary
- `P(like)`, `P(share)`, `P(follow_creator)` — positive secondary heads
- `P(skip < 3s)`, `P(complaint)` — negative heads
- Final ranking score = weighted combination, weights tuned via A/B

### High-level
Two-stage (plus re-ranker):
- Candidate generation: multiple sources → ~5,000 candidates
- Ranking: multi-task DNN → scores
- Re-ranker: diversity, freshness, creator cap, ad/organic blend

### Data & features

**Labels:**
- Positive: watched > 10s, liked, shared
- Negative: skipped within 3s (hard negative), explicit "not interested"
- Missing-negative trick: sampled negatives from the impression pool (items shown but not engaged)

**Features:**
- User: long-term embedding (learned), top-K watched creators, top categories, session-level recent views (last 20 reels)
- Item: visual embedding (pre-trained video encoder), audio embedding, caption text embedding, creator embedding, engagement velocity (views/like/share rate in last hour, last 24h)
- Context: time, device, network, session index (first reel vs 50th)
- User × item: cosine similarity of embeddings, past count of views from this creator, does user follow creator

**Freshness:** item engagement velocity recomputed every few minutes; user long-term profile daily; session features real-time.

### Modeling

**Candidate generation (parallel channels, top ~5k total):**
- Two-tower (user tower, item tower) → ANN over item embeddings (HNSW), retrieves top 2k
- Collaborative filtering from co-watch graph → 1k
- Followed creators' recent uploads → few hundred
- Trending in country / language → few hundred
- Random exploration bucket — critical for feedback loop mitigation

**Ranking: multi-task DNN with MMoE.**
- Shared bottom: concatenate all features → a few FC layers
- Experts (multi-gate mixture): N experts, each a small MLP
- Gating networks per task: weights which experts each task uses
- Task heads: separate MLP per task → sigmoid

Architecture sketch:
```
[user feats] [item feats] [context] [interaction] [history seq]
                           │
                           ▼
                   Embedding + concat
                           │
                           ▼
                   Shared FC layers
                           │
           ┌───┬───┬───┬───┬───┐  (N experts, MLPs)
           │   │   │   │   │   │
           ▼   ▼   ▼   ▼   ▼   ▼
         gate_watch   gate_like   gate_skip   ...
              │           │           │
              ▼           ▼           ▼
           head_watch  head_like   head_skip
              │           │           │
              ▼           ▼           ▼
           P(watch>10s) P(like)   P(skip<3s)
```

Loss: `L = α·BCE(watch) + β·BCE(like) + γ·BCE(share) − δ·BCE(skip)`, with α,β,γ,δ tuned.

Serving score: `score = w1·P(watch) + w2·P(like) + w3·P(share) − w4·P(skip)`, with weights A/B tuned (separate from training weights).

**User history sequence:** model recent N items with a transformer or DIN-style attention, where query = current candidate, keys/values = past items.

### Inference & evaluation

**Serving:** user request → candidate gen (~20 ms) → feature hydration (~30 ms, big fanout) → ranking (~50 ms on GPU) → re-ranker (~10 ms). Budget ~150–200 ms.

**Offline eval:** AUC per task, NDCG@10 using multi-objective utility as gain.

**Online eval:** A/B 1-2 weeks. Primary = watch time per session. Guardrails = complaint rate, unfollow rate, 7-day retention, creator concentration (Gini).

**Retraining:** daily batch retrain + hourly warm-start fine-tuning on last-hour engagement (for fast drift).

### Deep dives (be ready)

- **Position bias:** include slot index as a feature in training, fixed at inference
- **Clickbait / engagement-bait:** explicit "complained" / "not interested" signals as negative label; content-based classifiers to detect sensational content
- **Filter bubbles:** re-ranker enforces creator/topic diversity via MMR
- **Cold-start user:** heavy non-personalized + trending content, exploration on; onboarding signals (categories they followed)
- **Cold-start item:** content embeddings only, seeded exposure in exploration bucket
- **Feedback loops:** maintain an exploration budget (~5% of slots random or from exploration channels)
- **Feature freshness:** engagement velocity is critical for reels because items go viral within hours — recompute every few minutes
- **Creator fairness:** monitor gini of exposure across creators; consider creator promotion term in objective

---

## Case Study 2 — Feed Ranking (Facebook / Instagram main feed)

Very similar to reels but a few distinctions matter.

### Framing

**Clarify:**
- Mixed content types: posts, photos, videos, ads
- Items come from user's **friends + followed pages/accounts** (the candidate pool is smaller and pre-filtered by the social graph — this is a big difference from Reels)
- Latency: ~500 ms for page load
- Real-time inference

**Business objective:** Maximize meaningful social interactions (MSI) while maintaining session length and avoiding harmful-content exposure. (This is public: Meta famously shifted Feed to MSI around 2018.)

**ML objective:** Multi-task ranking. Predict probabilities of: comment, like, share, reshare-with-comment, click, dwell-time, hide, report. Weighted combination, with high weight on "effortful" interactions (comments, shares > passive likes).

### High-level

Candidate pool is already small-ish: posts from your network in the last N days, plus suggested content. Usually **no heavy retrieval stage** or a very light one; the heavy lifting is ranking.

```
User → Fetch candidates (friends/pages last 2 days, suggested)
     → Filter (already seen? hidden? integrity rules?)
     → Feature hydration
     → Multi-task ranking model
     → Re-ranker (diversity, integrity, ad mixing)
     → Render
```

### Data & features

**Labels:** comments, likes, shares, hides, reports (mostly implicit). "Integrity negatives" like report/hide are weighted heavily.

**Features:**
- User: same as reels + friends graph features, historical interaction with this author
- Item: post content embedding, media type, author account features, engagement velocity
- Edge (user × item): tie strength (frequency of past interactions with author), shared groups, mutual friends
- Context: time since post creation, recency in user's feed

Edge features are a distinguishing feature of feed — the **tie strength** between user and author is predictive.

### Modeling

**No heavy retrieval stage usually; candidate set is bounded by the social graph.**

Ranking = multi-task DNN, very similar to Reels. MMoE common. Sequence modeling over user's recent interactions.

**The "effortful interaction" weighting** — in the score combiner, comments > shares > likes (because commenting is a stronger signal of meaningful interaction). Weights tuned to maximize the MSI business objective.

### Inference, eval, deep dives

Mostly same as Reels. Two differences worth noting:

- **Integrity:** feed has a harder integrity problem because content from your network is sensitive. Multi-stage integrity filter before ranking.
- **Pagination / session modeling:** feed is sessions of multiple items viewed sequentially. Score decay for similar items already seen in session (diversity within session).

---

## Case Study 3 — Ad Click Prediction

Different from rec/feed because the **business objective is revenue**, and **calibration is critical** (because of auctions).

### Framing

**Clarify:**
- Surface: ads within feed / reels / search / sidebar
- Volume: billions of predictions/day
- Latency: very tight, often <100 ms — ads auctions run for every request
- Output: per-ad `P(click)` used in bidding: `eCPM = bid × P(click) × 1000`

**Business objective:** Maximize expected revenue per 1000 impressions (eCPM), conditional on ad quality (guardrail on user negative feedback + advertiser return).

**ML objective:** **Calibrated** binary classification — predict `P(click | user, ad, context)`. Calibration means the predicted probability equals the actual click rate in aggregate. This is essential because the bid × P(click) formula doesn't work if probabilities are off.

### High-level

```
Ad request → Eligible ad candidates (by targeting/geo/budget)
           → CTR model (predict P(click) per ad)
           → Auction: rank by bid × P(click), apply reserve price
           → Winning ad returned
           → Logged for training
```

Note: ad retrieval is by targeting rules (advertisers specify audience), not by model.

### Data & features

**Labels:** click (yes/no). Extremely imbalanced — click rate typically 1–5%.

**Features:**
- User: demographics, interests (from Feed/Reels behavior), historical CTR on ads in category X
- Ad: creative embedding (image/video/text), advertiser, category, landing page domain, historical CTR of this ad
- Context: surface, device, time, query (if search ads)
- Interaction: past user behavior with this advertiser

**Feature crosses** are historically critical for ads — user_age × ad_category, device × ad_format. This is why Deep & Cross / DeepFM emerged for ads.

### Modeling

**Baseline:** Logistic regression with hand-crafted crosses and L2. Still competitive. Google ran LR-based ad CTR for years.

**Stronger: Wide & Deep / DCN-v2 / DeepFM.**
- **Wide:** linear part with feature crosses (memorization of specific (user_segment, ad_id) pairs)
- **Deep:** MLP over embeddings for generalization

**Handling imbalance:**
- Downsample negatives at training
- **Crucial: re-calibrate at serving** because downsampling inflates P(click). Calibrate with isotonic regression on a held-out, un-downsampled set.

**Online learning** is common in ads because distributions shift fast (new ads, trends). FTRL (Follow The Regularized Leader) classic choice — scales to billions of features with sparsity.

### Inference & evaluation

**Latency:** extremely tight. Heavy use of:
- Feature caching
- Embedding table sharding
- Int8 quantization
- Sometimes distillation to a lighter model

**Offline eval:** AUC, log-loss. **Calibration is a first-class metric** — ECE (Expected Calibration Error), calibration plots.

**Online eval:** A/B test. Primary = revenue per thousand impressions. Guardrails = user complaints, advertiser ROI/long-term retention, click-to-conversion rate (not just click, actual outcome).

### Deep dives

- **Calibration:** always bring this up. Platt / isotonic. Why it matters (auctions).
- **Feedback loops:** the winning ad gets shown → you only see clicks for winners → training data is biased. Fix: exploration slots, inverse propensity scoring (IPS).
- **Delayed feedback:** conversions happen hours or days after click. Special modeling to handle censored labels.
- **Cold-start ad:** use creative embeddings + advertiser-level priors until enough impressions
- **Fraud / click farms:** separate classifier, filter before training

---

# Part 3 — Other question types (know the shape, 1-2 min skim each)

Questions you might get instead of the big three:

### Search ranking
Two-stage: lexical (BM25, inverted index) + semantic (dense retrieval / ANN over query-doc embeddings) → union → re-rank with learned-to-rank model. Metrics: NDCG, MRR. Query understanding is a whole sub-problem (typo correction, synonym, intent classification).

### People You May Know (PYMK)
Graph-based: candidate generation via friends-of-friends, group co-membership, workplace/school overlap. Ranking: probability of connection request → acceptance. Heavy graph features. Watch for privacy constraints.

### Harmful content / integrity
Classification, multi-label (hate, violence, nudity, misinfo). Ensembles of modality-specific classifiers (text, image, video, audio) → policy decision. Critical: precision/recall tradeoff very different (false positives remove benign content — costly). Human-in-the-loop review queue for borderline cases.

### Fraud / bot detection
Often graph + sequence. Account-level features + behavior sequence + device fingerprint. Very adversarial — constant cat-and-mouse. Anomaly detection layer + supervised classifier.

### ETA / delivery time (Uber, DoorDash style)
Regression. Features: distance, traffic, historical averages for route, time of day, weather, restaurant prep time. Multi-stage: predict pickup time + travel time separately, or end-to-end. Metrics: MAE, calibrated quantile predictions (for pessimistic ETAs users prefer).

### Dynamic pricing
Regression / RL. Features: demand signals, time, inventory, competitor prices. Often bandit / RL framing with exploration. Regulatory constraint: can't discriminate by protected class.

---

# Part 4 — 13-Day Study Plan

Assuming ~2h/day. Adjust up if you have more.

### Day 1: ML fundamentals + framework
- Read Part 0 (mindset), Part 1 (framework), and **Phase 0 (ML fundamentals)** in this doc
- Self-test: without looking, explain — overfitting vs underfitting, L1 vs L2, bias vs variance, when to use cross-entropy vs MSE, what dropout does
- If any of those are shaky, pause here and fix them before moving on

### Day 2: Framing fluency
- Read Phase 1 (Framing) and Phase 2 (High-level)
- Read the HelloInterview Delivery Framework page end-to-end
- Exercise: take 3 prompts (Reels, Feed, Ads) and **just write out the Framing phase** (clarify questions, business objective, ML objective) for each. 20 min each. Compare to case studies in Part 2.

### Day 3: Data & features fluency
- Read Phase 3 deeply, with extra attention to **3b-2 (feature transformations)** — the raw-signal-to-engineered-feature drill
- Read the Educative "Training Data Collection Strategies" and "Embeddings" lessons
- Exercise: for 5 raw signals (num_likes, session_count, last_login, user_age, item_upload_time), write out the senior-grade engineered version using the 11 transformation patterns

### Day 4: Modeling families + risks
- Read Phase 4 deeply, including **4f (model risks & mitigations)**
- External reading: skim Wide & Deep paper (just intro + architecture), skim DCN or DeepFM (architecture only), skim MMoE paper
- Exercise: for each of 3 prompts, name your baseline, chosen model family, 2 alternatives with tradeoffs, AND 3 risks with mitigations

### Day 5: Case Study — Reels / Video Recs (deep)
- Read Case Study 1 (Part 2) twice
- Read HelloInterview "Video Recommendations" problem breakdown
- Exercise: talk through it out loud, no notes, 45 min, with a timer. Record yourself or a whiteboard. Review.

### Day 6: Case Study — Feed Ranking (deep)
- Read Case Study 2
- Exercise: same out-loud walkthrough, 45 min

### Day 7: Case Study — Ad Click Prediction (deep)
- Read Case Study 3
- Exercise: same out-loud walkthrough, focus on calibration

### Day 8: Evaluation + debugging
- Read Phase 5 deeply, with extra attention to **5e (model debugging playbook)**
- Read HelloInterview "Evaluation" core concept
- Exercise: for each of the 3 prompts, write out the full offline + online eval plan with guardrails
- Drill the debugging ladder — have the 9-step diagnostic sequence memorized

### Day 9: Deep-dive patterns
- Read Phase 6 deeply
- Pick 3 deep dives you feel weakest on. Write a 1-paragraph explanation in your own words
- Flashcards: drill sections 1–4

### Day 10: Backend minimum + other problem shapes
- Read Part 5 (backend minimum) — 30 min max, don't over-invest
- Read Part 3 (other problem shapes)
- Pick 2 shapes (e.g. PYMK and harmful content) and do a 30-min Framing + High-level + Model skeleton each

### Day 11: Full mock #1
- Prompt yourself with "design a system to suggest groups for Facebook users to join" or similar
- 45 min with timer, fully out loud, whiteboard or paper
- Review against the framework — what phase did you skip? What tradeoff did you skip articulating? Did you volunteer risks and debugging?

### Day 12: Full mock #2
- Prompt: "design Meta's recommendation system for Threads' For You tab"
- 45 min, full mock
- Post-mortem: list the 5 weakest moments. For each, find the answer in this doc.

### Day 13: Flashcard blitz + weak-area reinforcement
- Flashcards in the companion file, both directions
- Re-read the 3 case studies one final time
- Drill the ML fundamentals from Phase 0 one more time (especially regularization, loss functions, bias/variance)
- Rest. Do NOT cram new content the day before.

---

# Part 5 — Backend minimum you need (don't over-invest)

Meta's ML track doesn't test deep distributed-systems knowledge, but you need the vocabulary so you can gesture confidently when the interviewer asks about serving. Minimum viable coverage:

**Storage:**
- **SQL** — transactional, joins, limited write scale. Not what you serve ML from.
- **Key-value (Redis, RocksDB)** — feature store lookups, caches, counters. Sub-ms reads.
- **Wide-column (Cassandra, HBase, Bigtable)** — massive append-heavy, time-series, logs
- **Object store (S3-like)** — training data, model artifacts, embeddings dumps
- **Vector DB / ANN index (FAISS, HNSW, ScaNN)** — item embedding lookup for retrieval

**Compute & serving:**
- **Model servers** — TorchServe, TF Serving, Triton, or custom
- **GPU vs CPU serving** — GPU for big DNNs, CPU often fine for small models + better cost/latency
- **Batching at inference** — group requests for throughput

**Streaming & queues:**
- **Kafka** — event log, backbone of training data collection. Topic, partition, consumer group.
- **Flink / Spark Streaming** — stream processing for near-real-time feature computation

**Observability (can gesture at but not needed deeply):**
- Metrics / logs / traces; p50/p99 latency; error rates; model-specific: prediction distribution drift, feature null rates

**Caching:**
- Client / CDN / reverse proxy / in-process / distributed (Redis) / DB
- Write strategies: through, back, around
- Invalidation: TTL + explicit

**Back-of-envelope estimates:**
- 1 day ≈ 10⁵ sec
- QPS ≈ (DAU × requests/user/day) / 10⁵
- Peak ≈ 2–3× average
- Example: 2B DAU × 50 reel-ranking requests/day ÷ 10⁵ = 1M QPS average, ~2–3M peak

That's it. If the interviewer goes deeper than this, acknowledge the limit of your backend depth and bring it back to the ML conversation: *"I'd lean on our ML infra team for the serving details; my focus has been on the model side."*

---

# Part 6 — The "I don't know" playbook

When you genuinely don't know something (it will happen):

1. **Acknowledge directly:** "I haven't worked on X personally."
2. **Generalize from what you do know:** "But the pattern looks similar to Y, where we'd do Z — I'd guess the same principle applies here."
3. **Name what you'd consult:** "I'd check recent blog posts from Meta/Google/Pinterest engineering on this, and look at papers from RecSys 2024/2025."

Interviewers have told me explicitly: they'd rather hire someone who can learn than someone who bluffs. Bluffing is the fastest way to fail. Authentic uncertainty + problem-solving fluency = senior signal.

---

# Part 7 — Red flags and green flags (self-check)

**🟢 Green flags in every phase:**
- Framing: you clarified before drawing; you named a guardrail; you translated business → ML precisely
- Data: you named label problems (missing negatives, position bias); you mentioned the 3 data buckets
- Modeling: you proposed a baseline; you offered 2+ options with tradeoffs; you picked one with a reason
- Eval: offline + online; you named guardrails; you mentioned A/B pitfalls (novelty, duration)
- Production: you mentioned feature freshness, cold start, feedback loops proactively

**🔴 Red flags:**
- Drawing boxes before clarifying
- Dumping 20 features without hypotheses
- Jumping to the latest model you read a blog post about
- Forgetting online evaluation
- Using "CTR" as both the business metric and the ML target without acknowledging the clickbait problem
- Calling your design "done" without mentioning monitoring or retraining
- Bluffing when asked about something you don't know

---

# Appendix — Glossary of terms you should be fluent in

- **Two-tower model** — user encoder + item encoder, similarity via dot product; used for retrieval with ANN
- **ANN (approximate nearest neighbor)** — sub-linear search for similar vectors; HNSW, ScaNN, FAISS are implementations
- **GBDT** — Gradient Boosted Decision Trees; XGBoost, LightGBM; strong tabular baseline
- **MMoE** — Multi-gate Mixture of Experts; multi-task architecture that allows tasks to share or diverge
- **Wide & Deep / DCN / DeepFM** — family of deep CTR prediction models that combine memorization and generalization
- **DIN/DIEN** — Deep Interest Network; attention over user behavior history
- **Sequence models for recsys** — SASRec, BST, HSTU; transformer-based next-item prediction
- **Multi-task learning** — one model, multiple heads, weighted loss; standard in feed/recs
- **Candidate generation / retrieval** — stage 1, fetch ~1000s from billions, cheap
- **Ranking** — stage 2, score ~1000s with heavy model
- **Re-ranking** — stage 3, apply diversity/business rules
- **Feature store** — unified system serving features consistently to training and inference (prevents train-serve skew)
- **Train-serve skew** — when feature computation differs between training and serving → silent bugs
- **Online vs batch features** — real-time vs pre-computed
- **Feature freshness** — how up-to-date features are at serving time
- **Embedding table** — huge lookup table mapping IDs (user, item) to learned dense vectors
- **Hashing trick** — for ultra-high-cardinality IDs, hash to a smaller fixed-size bucket before embedding
- **Position bias** — items shown higher get more clicks; training data is biased
- **Selection bias** — your training data only includes items your current model chose → feedback loop
- **Implicit feedback** — clicks, watches, dwells (as opposed to explicit ratings)
- **Calibration** — predicted probabilities match actual frequencies
- **Platt scaling / isotonic regression** — post-hoc calibration techniques
- **Exploration vs exploitation** — serving known-good items vs trying new ones; epsilon-greedy, Thompson sampling, UCB
- **Cold start** — new user or new item with no history
- **A/B test** — randomized controlled experiment between two model variants
- **Interleaving** — alternate model outputs within a single user session; more statistically sensitive than A/B
- **Shadow mode** — run new model in production without using its output; used for safety validation
- **NDCG / MAP / MRR** — ranking quality metrics (position-weighted)
- **AUC / PR-AUC** — classification quality; PR-AUC better for imbalanced
- **Knowledge distillation** — train small student model from large teacher
- **Quantization** — reduce numeric precision (fp32 → fp16 / int8) for speed
- **Drift** — distribution shift in features, predictions, or labels over time
