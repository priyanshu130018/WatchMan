# WatchMan Machine Learning Laboratory

Welcome to the **WatchMan ML Laboratory** (`notebooks/WatchMan_ML_Laboratory.ipynb`), an interactive engineering and research environment designed for manual inspection, debugging, profiling, and benchmarking of WatchMan's real machine learning and recommendation pipeline.

---

## 1. Purpose

The ML Laboratory provides an observation and experiment layer on top of WatchMan's production architecture:
- **Manual ML Experimentation**: Test embedding generation, candidate filtering, and ranking strategies interactively.
- **Diagnostics & Debugging**: Inspect real catalog embeddings, user taste vectors, interaction telemetry, and collaborative factor matrices.
- **Model & Dimension Evaluation**: Compare embedding models (e.g. `all-MiniLM-L6-v2` vs. `static-retrieval-mrl-en-v1`) and Matryoshka dimension truncations (1024, 512, 384, 256).
- **Latency & Performance Profiling**: Benchmark the latency of text preparation, embedding encoding, pgvector similarity queries, multi-channel candidate generation, and hybrid ranking.
- **Offline Recommendation Evaluation**: Measure Precision@K, Recall@K, and NDCG@K using genuine user interactions without manufacturing fake data.

---

## 2. Architectural Rule: Observation Layer Only

The ML Laboratory is an **OBSERVATION + EXPERIMENT** layer. 

```
                          TMDB Movie & Series Metadata
                                       │
                                       ▼
                             ┌───────────────────┐
                             │     contents      │
                             └─────────┬─────────┘
                                       │
                         ContentEmbeddingService
                         (all-MiniLM-L6-v2, 384-D)
                                       │
                                       ▼
                             ┌───────────────────┐
                             │content_embeddings │
                             └─────────┬─────────┘
                                       │
            ┌──────────────────────────┼─────────────────────────┐
            │                          │                         │
            ▼                          ▼                         ▼
   Content-Based Channel      Popularity Channel         Freshness Channel
   (Dense Cosine Search)      (TMDB Popularity)          (Release Recency)
            │                          │                         │
            └──────────────────────────┼─────────────────────────┘
                                       │
                                       ▼
  Real User Behavioral Signals ──► CandidatePipeline
  - Watch progress (>=40%)             │
  - Saved to Watchlist                 ▼
  - User Ratings (>=6.0)     ALSCollaborativeChannel
  - Watchman Decisions                 │
            │                          ▼
            ├──► UserEmbeddingService (384-D)
            │                          │
            └──► ALSTrainingService    ▼
                 (Implicit ALS Factors)│
                                       │
                                       ▼
                                 HybridRanker
                 (Content 40% + Collab 30% + Pop 15% + Fresh 10% + Pref 5%)
                                       │
                                       ▼
                             ┌───────────────────┐
                             │  recommendations  │
                             └───────────────────┘
```

**Key Architectural Rules:**
1. **No Duplication of Production Algorithms**: The notebook directly imports production backend services (`ContentEmbeddingService`, `UserEmbeddingService`, `CandidatePipeline`, `HybridRanker`, `ALSTrainingService`, etc.).
2. **Production Logic Stays in Backend**: Production algorithms remain in `backend/app/ml/`. The notebook only observes and invokes those services.

---

## 3. Safety Guarantees

> ⚠️ **Strict Safety Constraints**
> 
> - **NOT part of Docker startup**: Will never run during `docker compose up`.
> - **NOT part of FastAPI startup**: Does not attach to the web API lifecycle.
> - **NOT part of Celery worker/beat**: Independent of background tasks.
> - **NOT part of CI/CD or deployment**: Tests and builds do not depend on it.
> - **Zero Synthetic Production Records**: Never inserts fake users, fake ratings, or fake content into PostgreSQL.
> - **Default Read-Only**: `READ_ONLY = True` and `ALLOW_DB_WRITES = False`.
> - **Explicit Write Lock**: Any cell that touches the database requires an explicit manual toggle and will raise an exception otherwise.
> - **No Table Truncation or Deletion**: Deletion or table wiping from the notebook is prohibited.

---

## 4. What the Laboratory Can Inspect and Benchmark

### Inspection Capabilities
- **Content Embeddings**: Inspect 384-dimensional vectors, text representations (`build_movie_embedding_text`), and SHA-256 hashes in `content_embeddings`.
- **User Embeddings**: Inspect dynamic 384-D preference vectors built from real watch history, bookmarks, ratings, and WatchMan decisions.
- **Interaction Telemetry**: Inspect `interaction_events`, `saved_content`, `ratings`, `watch_history`, and `watchman_decisions`.
- **Recommendation Scores**: Inspect multi-channel candidate scores (Content, Collaborative, Popularity, Freshness, Taxonomy Preference) and final composite ranks.
- **ALS Factors**: Inspect latent user factor matrix `(n_users, k)` and item factor matrix `(n_items, k)` in `als_user_factors` and `als_item_factors`.
- **Persisted Recommendations**: Compare freshly generated hybrid scores against stored records in `recommendations`.

### Benchmarking Capabilities
- **Embedding Models**: Compare inference throughput, latency per item, and vector footprint between `all-MiniLM-L6-v2` and `static-retrieval-mrl-en-v1`.
- **Matryoshka Dimensionality**: Evaluate vector truncation across 1024, 512, 384, and 256 dimensions.
- **Pipeline Latency**: Multi-stage profiling of text preparation, candidate generation, vector search, and hybrid ranking with warmup (3 runs) and benchmark iterations (20 runs).
- **Ranking Metrics**: Precision@K, Recall@K, and NDCG@K evaluated on real user feedback.

---

## 5. Notebook Structure (22 Sections)

1. **WatchMan ML Laboratory**: Safety warning and architecture diagram.
2. **Environment & Safety**: Safety switches (`READ_ONLY = True`, `ALLOW_DB_WRITES = False`), reproducibility config, and diagnostic prints.
3. **Database Connection**: Safe connection management using `get_session()` with masked credentials.
4. **Catalog Overview**: Tabular counts across all 16 key tables and a real TMDB catalog sample.
5. **Content Embedding Experiments**: Inspection of metadata-to-text extraction via `build_movie_embedding_text`.
6. **Inspect Existing Content Embeddings**: Reading and statistics of stored vectors from `content_embeddings`.
7. **Generate an Embedding Manually**: Manual inference via `SentenceEncoder` with dimension, norm, min/max, mean/std.
8. **Save / Read Embeddings from PostgreSQL**: Vector comparison, cosine similarity, and write-guarded persistence demo.
9. **Content Similarity Search**: Top-K nearest neighbor search via `ContentEmbeddingService.search_by_vector` and pure-Python verification.
10. **User Taste Embedding**: Behavioral signal weighting (`UserEmbeddingService.get_user_interaction_weights`).
11. **User Interaction → User Embedding**: In-memory taste vector aggregation and comparison with stored vectors.
12. **Recommendation Score Calculation**: Verification of production blend weights (Content 40%, Collab 30%, Pop 15%, Fresh 10%, Pref 5%).
13. **Hybrid Recommendation Pipeline**: Multi-channel candidate retrieval and ranking for a selected user.
14. **Content-Based Filtering Experiment**: Content-to-content vs. User-to-content similarity comparison.
15. **Collaborative Filtering / ALS Experiment**: ALS training threshold checks (`min_users=3, min_items=3, min_interactions=10`) and factor calculation.
16. **Hybrid Content + Collaborative Experiment**: Overlap analysis (items in both channels, content-only, collaborative-only, hybrid coverage).
17. **Recommendation Evaluation**: Precision@K, Recall@K, and NDCG@K metrics on real user positive signals.
18. **Embedding Model Benchmark**: Inference throughput, ms/item, and storage comparison across models and Matryoshka dimensions.
19. **Latency Benchmark**: Profiling text preparation, candidate retrieval, and hybrid ranking across 20 iterations.
20. **Experiment Results & Export**: Visual charts (matplotlib) and CSV export to `notebooks/results/`.
21. **Cleanup / Safety**: Post-run verification that 0 rows were altered in the database.
22. **Notes & Conclusions**: Key architectural findings and production guidelines.

---

## 6. How to Run the Laboratory

### Prerequisites
Ensure your database (Supabase / PostgreSQL) is configured in your `.env` or `backend/.env`.

### Step 1: Install Notebook Dependencies
```bash
pip install -r notebooks/requirements.txt
```
*(Or install `jupyter`, `ipykernel`, `pandas`, `matplotlib` in your backend virtualenv)*

### Step 2: Register the Kernel (Optional if using virtual environment)
```bash
python -m ipykernel install --user --name=watchman-ml --display-name="Python 3 (WatchMan)"
```

### Step 3: Launch Jupyter Lab / Notebook
From the repository root:
```bash
jupyter lab notebooks/WatchMan_ML_Laboratory.ipynb
```
or
```bash
jupyter notebook notebooks/WatchMan_ML_Laboratory.ipynb
```

### Step 4: Run Cells
1. Check Section 2 output to confirm `READ_ONLY = True` and database target.
2. Execute cells section by section.
3. Exported benchmark artifacts will be saved to `notebooks/results/`.
