# System Design Crash Course — Datadog Edition

---

# Part 0 — Foundation

## The S.O.L.I.D. framework (Datadog's official structure)

Datadog's prep guide explicitly tells you to use this 5-step structure. Memorize the letters.

1. **S — Scope the problem.** Clarify requirements. Functional ("what does it do?") and non-functional ("how well — scale, latency, consistency?"). Don't draw anything yet.
2. **O — Outline high-level design.** Sketch the boxes: clients, API layer, services, stores. ~5 boxes max in this pass. Talk through the data flow.
3. **L — List data storage & APIs.** Pick your databases with justification, sketch the main API endpoints, mention caching layer if needed.
4. **I — Identify scaling & performance optimizations.** Where does this break at 10×? Sharding, replication, caching, async processing, CDN.
5. **D — Discuss monitoring & failure handling.** What metrics? What happens when components fail? Retries, circuit breakers, replicas, dead-letter queues.

50 min of design time, so rough budget: S ~7 min, O ~10 min, L ~10 min, I ~15 min, D ~8 min. The interviewer will probably interrupt and pull you into deep dives — that's good, follow them.

**Key takeaway:** S.O.L.I.D. is the contract. Hitting all five letters = passing structure, even if depth varies.

---

## The 8 pitfalls Datadog explicitly grades against

From the official Datadog prep guide. Each one is a specific behavior that flags you as junior. Memorize the inverses as habits.

1. **Not clarifying the problem** → Always ask 3-5 clarifying questions before drawing.
2. **Jumping into architecture without requirements** → State functional + non-functional reqs out loud first.
3. **Poor scalability** → Always mention load balancing, sharding, caching, horizontal scaling.
4. **Storage choice without justification** → Never say "I'll use Postgres" without a reason; always pair the choice with the property you need (consistency, query patterns, scale).
5. **Ignoring failure scenarios** → Proactively address replication, failover, retries, timeouts, circuit breakers.
6. **Not addressing observability** → Mention metrics, logging, alerting. **At Datadog, mention Datadog APM by name where natural.**
7. **No tradeoff analysis** → Every choice has an alternative; name what you gave up.
8. **Poor communication** → Use S.O.L.I.D. structure; narrate your thinking out loud.

**Key takeaway:** these aren't soft preferences — they're explicit grading criteria from the company itself.

---

## Functional vs non-functional requirements

The first thing you do in the Scope phase. Write both down before drawing anything.

**Functional requirements** = what the system does. Verbs and nouns.
- "Users can shorten a URL"
- "Users can retrieve original URL from short code"
- "URLs expire after a configurable TTL"

Cap functional reqs at 3-5. More = scope creep. Ask the interviewer "should I include analytics?" rather than assuming.

**Non-functional requirements** = how well it does it. Numbers and qualities.
- **Scale:** DAU, peak QPS read, peak QPS write, total data
- **Latency:** p50 and p99 (p99 is what users feel)
- **Availability:** 99.9% (8.7h down/year) vs 99.99% (52 min/year)
- **Consistency:** strong vs eventual
- **Durability:** can we lose data?
- **Security/privacy:** PII handling, auth model

The non-functional list is what unlocks design choices. "Read-heavy?" → caching. "Strong consistency?" → not eventual replication. "100M DAU?" → sharding from day one.

**Always ask: "is this read-heavy or write-heavy?"** It's the single highest-information clarifying question.

**Key takeaway:** if you skip non-functional reqs, every design choice afterward is unjustified.

---

## Back-of-envelope estimation

You don't do this upfront — Datadog and HelloInterview both say not to lead with estimation. You do it **when a design decision needs a number**: do we shard? do we cache? how many servers?

**Time conversions to memorize:**
- 1 day ≈ 10⁵ seconds (86,400, round to 100k)
- 1 month ≈ 2.5 × 10⁶ seconds
- 1 year ≈ 3 × 10⁷ seconds

**The QPS formula:**
- Average QPS ≈ (DAU × requests per user per day) / 10⁵
- Peak QPS ≈ 2-3× average

**Example workflow:**
- "100M DAU, each user posts 10 times/day"
- → 1B writes/day ÷ 100k = 10k writes/sec average
- → ~25-30k peak QPS

**Storage:**
- 1 KB metadata per record × 1B/day = 1 TB/day = ~365 TB/year
- 200 KB media × 1B/day = 200 TB/day → object store, not DB

**The interviewer wants to see math, not memorized facts.** Walk through it: "1B records/day, 1 KB each, that's 1 TB/day — at 5 years retention we're at ~2 PB, which means we need sharded storage and an object store for the media."

**Key takeaway:** estimation is a tool to justify a decision, not a checkbox to tick at minute 5.

---

## Communication habits that signal seniority

The interviewer is grading clarity of thought as much as content. These habits move you up a level even when your knowledge is the same.

**Narrate before you draw.** "I'm thinking we need a write-heavy storage layer because of [reason], so I'll reach for Cassandra. Let me sketch that out."

**Pre-announce structure.** "I'll spend ~5 min on requirements, then sketch the high level, then we can go deep wherever you want."

**Ask permission to commit.** "Does it sound reasonable to assume strong consistency for the payments path? OK, then I'll use Postgres with synchronous replication."

**Surface tradeoffs unprompted.** "I'm picking Kafka over RabbitMQ because we need replay and high throughput, but the tradeoff is operational complexity and we lose the easy fanout of RabbitMQ exchanges."

**When stuck, say so.** "Give me a few seconds to think through this." Beats bluffing every time.

**When you don't know.** "I haven't worked with X directly, but the pattern looks like Y, where I'd do Z." Authentic uncertainty + reasoning = senior signal.

**Time-box your own deep dives.** "I could go deeper on the sharding scheme, but I want to make sure we cover failure modes too — should I move on or stay here?"

**Key takeaway:** how you talk through the design carries as much weight as the design itself.

---

# Part 1 — Core building blocks

## Numbers to know — latency hierarchy

These are the "Jeff Dean numbers." Memorize them. They drive every "should I cache / shard / use a CDN" decision.

| Operation | Time | Mental model |
|---|---|---|
| L1 cache reference | ~1 ns | Instant |
| L2 cache reference | ~4 ns | Instant |
| Main memory access | ~100 ns | Very fast |
| SSD random read | ~100 µs (0.1 ms) | Fast |
| Roundtrip same datacenter | ~0.5 ms | Fast |
| Read 1MB sequentially from SSD | ~1 ms | Quick |
| HDD seek | ~10 ms | Slow |
| Roundtrip US east → west coast | ~70 ms | Slow |
| Roundtrip cross-continent | ~150 ms | Painful |

**Rules of thumb derived from these:**
- Memory is ~1000× faster than disk → cache hot data
- Same-DC network is ~5× slower than disk → batch DB calls
- Cross-region is ~300× slower than same-DC → put data near users (CDN, regional replicas)
- Speed-of-light limit: NYC → London is ~40ms minimum no matter what

**Interview application:** when proposing geo-distribution, say "cross-continent latency is ~150ms, so a synchronous write across regions adds 150ms to every request — we need async replication or regional ownership."

**Key takeaway:** latency numbers are the physics constants of system design. Everything else follows from them.

---

## Numbers to know — throughput & capacity

Modern hardware is way more capable than candidates assume. Using 2010 numbers makes you propose sharding way too early.

**Per-server limits (well-tuned, single instance):**

| Component | Throughput | Capacity |
|---|---|---|
| Postgres / MySQL | 10-50k QPS | up to ~64 TiB |
| Redis | 100-200k+ ops/sec | memory-bound, up to ~1 TB |
| Cassandra (per node) | 10-20k writes/sec | many TB |
| Kafka (per broker) | up to 1M msgs/sec | up to ~50 TB |
| App server (Go/Java) | 10-50k QPS | 100k+ concurrent connections |
| Load balancer (nginx, HAProxy) | 100k+ QPS | basically unbounded for L4 |
| S3 / object storage | basically unbounded | basically unbounded |

**When to scale (rough triggers):**
- DB write throughput >10k QPS → start thinking sharding
- DB read latency >5ms uncached → add cache or replicas
- Cache hit rate <80% → revisit cache strategy
- App server CPU >70% sustained → add instances
- Kafka consumer lag growing → add partitions/consumers

**Interview application:** if your scale is 5k QPS, do NOT propose sharding. A single Postgres handles that. Say "5k QPS is well within a single Postgres node's capacity, so I'll use a single primary with read replicas instead of sharding."

**Key takeaway:** know the per-server ceilings. Scale up before scaling out — it's simpler and usually enough.

---

## Database indexing — B-tree fundamentals

An index is a separate sorted data structure that maps from a column value → row location. Without an index, finding a user by email = full table scan (10M rows = 10M comparisons). With an index, it's tree traversal (~24 comparisons for 10M rows).

**B-tree (the default for relational DBs):**
- Self-balancing tree, kept sorted
- Each node holds many keys (hundreds), so tree stays shallow even at huge scale
- Supports **exact match** (`WHERE email = 'x'`) AND **range queries** (`WHERE date BETWEEN A AND B`) AND **ORDER BY** on the indexed column
- O(log n) lookups, O(log n) inserts/updates

**Hash index:**
- O(1) exact match, but no range queries, no ORDER BY
- Postgres has them; rarely worth it because B-tree is nearly as fast for points and far more useful

**Cost of indexes:**
- Every write must update every index → write amplification
- Indexes take storage (often ~10-30% of table size)
- Query planner has to choose, can pick poorly

**Rule of thumb:** index columns you query and order by frequently; don't index everything.

**LSM-tree** (Cassandra, RocksDB, LevelDB): a different approach optimized for writes. Writes go to in-memory memtable → flushed to immutable SSTables on disk → background compaction merges them. Very fast writes, slower reads (may check multiple SSTables; Bloom filters help). This is why Cassandra excels at write-heavy workloads.

**Key takeaway:** B-tree for read-heavy or balanced; LSM for write-heavy. Both are O(log n) but with very different write profiles.

---

## Database indexing — composite, covering, partial

Beyond single-column indexes, three patterns matter in interviews.

**Composite index** (multi-column):
- Index on `(country, city, created_at)` covers queries on:
  - `WHERE country = ?`
  - `WHERE country = ? AND city = ?`
  - `WHERE country = ? AND city = ? AND created_at > ?`
- Does NOT cover `WHERE city = ?` alone — leftmost-prefix rule
- Order matters: most-selective column first usually, but follow your query pattern

**Covering index** (a.k.a. "index-only scan"):
- The index itself contains all columns the query needs, so the DB doesn't read the table at all
- Postgres: `CREATE INDEX ... INCLUDE (col1, col2)`
- Huge speedup on read-heavy paths
- Tradeoff: bigger index, slower writes

**Partial index:**
- Index only rows matching a predicate: `CREATE INDEX ... WHERE deleted_at IS NULL`
- Saves space when most rows don't need indexing (e.g., 99% of orders are completed; only index pending ones)

**Specialized indexes:**
- **Full-text** (Postgres `tsvector`, Elasticsearch): word-level search
- **Geospatial** (PostGIS, MongoDB 2dsphere): "find within 5km"
- **GIN/GiST** (Postgres): arrays, JSONB, full-text

**External search index:**
- For full-text or complex search at scale, sync from primary DB to Elasticsearch via change data capture (CDC). The search index lags slightly; usually fine.

**Key takeaway:** composite indexes follow query patterns; covering indexes save table reads; partial indexes save space. Mention the right one when the query pattern calls for it.

---

## Database indexing — when NOT to index

A common interview trap is over-indexing. Knowing when *not* to add an index is senior signal.

**Don't index when:**
- **Low-selectivity columns** (e.g., a boolean `is_active` where 90% are true). The index doesn't narrow much; full scan may be faster.
- **Tiny tables** (<10k rows). Linear scan is fast; index adds maintenance overhead for no benefit.
- **Write-heavy tables with rare reads.** Each write updates the index. If you read once a day, the write tax isn't worth it.
- **Columns with frequent updates.** Updates to indexed columns are extra-expensive (index reorder).
- **You can use a covering or composite index instead.** Don't pile up single-column indexes when one composite covers them.

**Cost of getting it wrong:**
- 10 indexes on a write-heavy table = ~10× write amplification
- Storage cost: 10 indexes × 20% of table size each = 2× the data on disk
- Query planner may pick a bad index, making things slower than no index at all

**Diagnostic in production:** in Postgres, `pg_stat_user_indexes` shows unused indexes. Drop them.

**Interview habit:** when proposing an index, justify *why this column* and *why now*. "We're querying `user_id` on every page load, so a B-tree index on `user_id` makes that O(log n)." Don't just sprinkle indexes everywhere.

**Key takeaway:** indexes are not free. Every one is a tradeoff between read speed and write cost.

---

## SQL vs NoSQL — the decision tree

This decision shows up in every interview. Memorize the heuristic.

**Pick SQL (Postgres, MySQL) when:**
- Data is **relational** (entities link to each other: users → orders → products)
- You need **transactions** (ACID — money, inventory, multi-step ops)
- You need **strong consistency**
- Query patterns are **flexible/ad-hoc** (you don't know all queries upfront — SQL handles unknown queries; NoSQL doesn't)
- Scale is **moderate** (<TBs, <10k QPS writes) — single Postgres handles a LOT

**Pick NoSQL when:**
- Scale is **massive** (PBs, 100k+ QPS writes) and you can't fit on one box
- Access patterns are **simple and known upfront** (key lookups, append-only logs)
- Schema is **flexible** (rapidly changing data shape)
- You need **horizontal scale** as a baseline, not an afterthought

**Within NoSQL, four flavors:**
- **Key-value** (Redis, DynamoDB) — fastest, simplest. Sessions, caches, counters, simple lookups.
- **Document** (MongoDB) — JSON blobs with secondary indexes. Flexible schema, semi-structured data.
- **Wide-column** (Cassandra, HBase, Bigtable) — massive scale, append-heavy, time-series. Tunable consistency.
- **Graph** (Neo4j) — relationships first-class. Social graphs, fraud detection.

**Common mistake:** picking NoSQL "because scale." A single Postgres can handle most apps you'll ever build. Default to SQL unless you have a specific reason.

**Common combination (polyglot persistence):** Postgres for the source of truth + Redis for cache + Elasticsearch for search + S3 for blobs. This is normal, not over-engineering.

**Key takeaway:** SQL is the safe default for moderate scale and relational data. Reach for NoSQL when you have a specific access pattern that SQL handles poorly.

---

## Caching — strategies (cache-aside, write-through, write-back)

Caching is in 90% of interviews. Three patterns, each with a clear use case.

**Cache-aside (lazy loading) — the default 90% of the time:**
1. Read: check cache → if hit, return; if miss, read DB, write to cache, return
2. Write: update DB → invalidate cache entry
3. Pros: simple, only caches what's actually read, cache failure ≠ data loss
4. Cons: first read after write is a miss (cold cache); stale data if invalidation fails

**Write-through:**
1. Write: update cache AND DB synchronously
2. Read: always read from cache
3. Pros: cache is always consistent with DB, no cold misses for written data
4. Cons: every write pays the latency of two systems; cache failure = write fails

**Write-back (write-behind):**
1. Write: update cache → mark dirty → async flush to DB later
2. Pros: very fast writes (cache speed), can batch DB writes
3. Cons: data loss if cache crashes before flush; complex consistency
4. Use for: write-heavy non-critical data (analytics counters, view counts)

**Write-around:**
1. Write: skip cache, write only to DB; cache fills on next read
2. Use for: data that's written once, rarely re-read (logs, audit trails)

**Eviction policies:**
- **LRU** (Least Recently Used) — default, works well most of the time
- **LFU** (Least Frequently Used) — better for skewed access (Zipf-like)
- **TTL** (time-based expiry) — required when you can't manually invalidate
- Production usually combines: LRU + per-key TTL

**Key takeaway:** cache-aside + Redis + LRU + TTL is your default answer. Reach for write-through only when staleness is unacceptable.

---

## Caching — invalidation & stampedes

"There are only two hard things in computer science: cache invalidation and naming things." Know the failure modes.

**Cache invalidation strategies:**
- **TTL only** — accept staleness up to TTL. Simple, but max stale = TTL.
- **Explicit invalidation on writes** — delete cache key when DB updates. Tighter consistency but harder if multiple writers.
- **TTL + explicit invalidation** — belt and suspenders. The standard production pattern.
- **Versioning** — bake a version into the cache key (`user:42:v3`). Old keys naturally age out. Useful when invalidation is hard.

**Cache stampede / thundering herd:**
A hot key expires → 10,000 concurrent requests miss the cache → all 10,000 hit the DB simultaneously → DB falls over.

**Fixes:**
- **Request coalescing:** first miss locks, subsequent misses wait for the first to populate the cache. Most clients (e.g., `singleflight` in Go) provide this.
- **Probabilistic early expiration:** as TTL approaches, randomly refresh some requests early. Spreads the refresh load.
- **Stale-while-revalidate:** serve stale value while a background job refreshes. Trades some staleness for zero stampedes.
- **Cache warming:** pre-populate cache on deploy or schedule for known-hot keys.

**Hot key problem:**
One key gets 100× the traffic of others. A celebrity's profile, a viral tweet.
- **Local in-process cache** in front of distributed cache (extra layer = extra speed for hot keys)
- **Key splitting / sharding the value:** `user:42:shard1`, `user:42:shard2`, app reads from a random shard

**Cache penetration:**
Lookups for keys that don't exist hit DB every time (cache always misses).
- Cache the negative result (with shorter TTL)
- Use a Bloom filter to short-circuit "definitely doesn't exist"

**Key takeaway:** "TTL + explicit invalidation" is the standard. Mention stampede protection (request coalescing) when you have hot keys.

---

## Sharding — strategies and tradeoffs

Sharding splits data across multiple databases when one isn't enough. The shard key choice determines everything else.

**When to shard:**
- Storage: single Postgres can handle ~64 TiB. Shard if you'll exceed that.
- Writes: single primary can handle ~10-50k QPS writes. Shard if higher.
- **Don't shard prematurely.** Vertical scaling + read replicas handle most apps. Sharding adds massive operational complexity.

**Sharding strategies:**

**1. Range-based:**
- Shard A: user_id 1-1M, Shard B: 1M-2M, etc.
- Pros: simple; easy range queries within a shard
- Cons: hot spots (newest users get all writes if range = recency)

**2. Hash-based:**
- `shard = hash(user_id) % N`
- Pros: even distribution, no hot spots
- Cons: range queries become scatter-gather; adding a shard reshuffles everything (use consistent hashing)

**3. Consistent hashing:**
- Place shards and keys on a virtual ring; key goes to next shard clockwise
- Adding/removing a shard moves only ~1/N of keys instead of nearly all
- Used by Cassandra, DynamoDB, Memcached
- This is the answer when interviewer asks "what about adding a shard?"

**4. Directory-based:**
- Lookup table maps key → shard
- Pros: max flexibility (rebalance freely)
- Cons: lookup adds latency; lookup table is a bottleneck/SPOF

**Picking the shard key:**
- Pick a key with **high cardinality** (lots of distinct values)
- Pick a key that **distributes evenly** (no celebrity hot keys)
- Pick a key that **co-locates queries** (for a user-centric app, `user_id` keeps a user's data on one shard)

**The classic gotcha:** cross-shard queries / transactions. Shard by user_id and now "find all posts mentioning hashtag X" requires hitting every shard. Designing the shard key to match your query patterns is the whole game.

**Key takeaway:** consistent hashing + a query-aligned shard key. Justify sharding with numbers — don't propose it for a 5k-QPS app.

---

## Replication — leader-follower, multi-leader, leaderless

Replication = multiple copies of data for availability and read scaling. Three models with different consistency tradeoffs.

**Leader-follower (a.k.a. primary-replica) — most common:**
- All writes go to leader; leader replicates to followers
- Reads can hit either (followers may be slightly stale = replication lag)
- **Sync replication:** leader waits for at least one follower to ack before confirming write. Slower, no data loss on leader failure.
- **Async replication:** leader confirms immediately, replicates in background. Faster, can lose recent writes if leader crashes.
- **Failover:** when leader dies, promote a follower. Manual or automated (with consensus like Raft to avoid split-brain).
- Used by: Postgres, MySQL, MongoDB

**Multi-leader:**
- Multiple nodes accept writes
- Conflicts must be resolved (last-write-wins, CRDTs, application-level merge)
- Use case: multi-datacenter setups where each region has a local leader
- Rare in interviews; mention only if the problem demands it (collaborative editing, multi-region writes)

**Leaderless (Dynamo-style):**
- Any node accepts any read or write
- Quorum-based: write to W nodes, read from R nodes; if W + R > N, you read at least one node with the latest write
- Conflicts resolved by version vectors / vector clocks
- Used by: Cassandra, DynamoDB, Riak

**Replication factor:** how many copies. Standard = 3 (survives 1 failure with strong guarantees, 2 failures with degraded service).

**Read-your-writes consistency:** a user must see their own writes immediately. With async replication, route a user's reads to the leader for a short window after their write.

**Key takeaway:** leader-follower with async replication is the default. Sync if you can't lose writes; quorum/leaderless if you need write availability across regions.

---

# Part 2 — The 7 Patterns (HelloInterview locked content)

## Pattern — Real-time updates

When a user sees data update without refreshing. Maps to: live scores, chat, notifications, live dashboards (like Datadog metrics), collaborative editing.

**The four mechanisms (from cheap to expensive):**

**1. Polling.** Client asks server every N seconds. Simple, terrible at scale (N×clients useless requests).
- Use only for: low frequency (every minute+), few clients, when easier than alternatives.

**2. Long polling.** Client requests; server holds the connection until data is ready or timeout (~30s); client re-requests immediately. Looks real-time but uses standard HTTP.
- Use for: moderate scale, simple infra (no WebSocket support needed), updates per minute or so.

**3. Server-Sent Events (SSE).** Server pushes a one-way event stream over HTTP. Browser-native (`EventSource`). Reconnection built-in.
- Use for: server → client only updates (notifications, live feeds, metric streams). Simpler than WebSockets.

**4. WebSockets.** Full-duplex, persistent TCP connection. Both sides send messages freely.
- Use for: bidirectional real-time (chat, multiplayer, collaboration). The "right" answer when both directions need to push.

**Scaling considerations:**
- Persistent connections (SSE/WebSocket) need sticky load balancing (L4) — can't randomly reroute mid-connection.
- 100k+ concurrent connections per server is achievable with the right runtime (Go, Node, Erlang); design for connection limits.
- For pub/sub fanout to many clients: an internal message bus (Redis pub/sub or Kafka) → connection servers → clients.

**Common mistake:** reaching for WebSockets when SSE or long polling would do. WebSockets = significant infrastructure complexity (sticky LB, connection state, scaling). Use them only when you genuinely need bidirectional.

**Key takeaway:** SSE for one-way push; WebSocket for two-way; long polling when infra is constrained.

---

## Pattern — Dealing with contention

When multiple actors try to modify the same resource simultaneously. Maps to: ticket booking, inventory, payments, leaderboards.

**The problem:** without coordination, two users buy the last ticket; or a counter increments incorrectly.

**Solutions, from light to heavy:**

**1. Atomic operations in the DB.**
- `UPDATE counters SET value = value + 1 WHERE id = ?` — atomic at the DB level
- Postgres: `SELECT ... FOR UPDATE` row-level lock
- Redis: `INCR`, `DECR` are atomic; Lua scripts for multi-step atomicity

**2. Optimistic concurrency control (OCC):**
- Read row with a version/timestamp
- On write: `UPDATE ... WHERE version = old_version`
- If 0 rows updated, someone else got there first → retry
- Good for low contention; cheap when conflicts are rare

**3. Pessimistic locking:**
- Acquire a lock before reading; release after writing
- DB row locks (`FOR UPDATE`) or external (Redis with `SET NX`)
- Good for high contention but blocks other actors → reduces throughput

**4. Distributed locks (Redis, ZooKeeper):**
- For coordinating across services
- **Always include a TTL** (lock auto-expires) to avoid deadlock if the holder crashes
- Redlock pattern (using multiple Redis nodes) for stronger guarantees; debated whether it's worth the complexity

**5. Single-writer pattern:**
- Route all writes to one resource through a single actor (e.g., per-shard worker, or partitioned Kafka consumer)
- No locks needed — the single-writer serializes operations
- Common in event-sourced systems

**6. Reserve-then-confirm (for tickets/inventory):**
- Step 1: reserve item with a TTL (5 min)
- Step 2: user confirms → reservation becomes purchase
- Unclaimed reservations expire and return to inventory
- Avoids holding a row lock for 5 minutes

**Key takeaway:** match the heaviness to actual contention. Atomic ops > OCC > pessimistic locks. Distributed locks are last resort.

---

## Pattern — Multi-step processes

When a single user action requires multiple sequential operations across services, possibly with failures in between. Maps to: order placement (charge card → reserve inventory → ship), signup flows, complex business workflows.

**The problem:** if step 3 fails, you need to undo steps 1 and 2 — but they may be on different services with no shared transaction.

**Solutions:**

**1. Saga pattern (the standard answer).**
- Each step has a corresponding compensating action that undoes it
- If a step fails, run compensations for all completed steps in reverse
- Two flavors:
  - **Choreography:** each service emits an event; next service listens and acts. Decentralized.
  - **Orchestration:** a central coordinator service runs the saga and handles compensations. Easier to reason about, common in interviews.

**2. State machine + persistent state.**
- Persist the workflow state (e.g., "order: payment_pending → payment_complete → reserving_inventory → ...")
- A worker picks up where it left off after a crash
- Often built on a workflow engine: Temporal, AWS Step Functions, Cadence

**3. Event sourcing.**
- Every state change = an immutable event in a log
- Current state = replay all events
- Naturally supports retries (events are idempotent if processed by ID)

**Idempotency is mandatory:**
- Each step must be safe to retry. Use idempotency keys (`order_id`) so retries don't double-charge.
- "At-least-once" delivery is normal; design for it.

**Outbox pattern (when DB write must trigger an event):**
- Write the event into an "outbox" table in the same transaction as the DB write
- A separate poller reads outbox → publishes to Kafka → marks done
- Avoids the dual-write problem (DB write succeeds, event publish fails)

**Key takeaway:** Saga + idempotent steps + persistent state = reliable multi-step workflows. Mention Temporal as a real-world tool.

---

## Pattern — Scaling reads

When read traffic exceeds what one DB can handle. Usually the easier scaling problem (writes are harder). Maps to: most read-heavy apps, content sites, social feeds.

**The toolkit, in order of complexity:**

**1. Cache.** First and often last resort. Redis in front of DB, cache-aside pattern. Hit rate >90% means DB sees only 10% of the original load.

**2. Read replicas.**
- DB primary handles writes; followers serve reads
- Apps split: writes → primary, reads → any replica
- Replication lag: reads may be stale by milliseconds to seconds (eventual consistency)
- Read-your-writes: route a user's reads to primary briefly after their write

**3. CDN for static/cacheable content.**
- Edge servers cache responses near users
- Massive offload for images, videos, but also cacheable API responses
- Cache key includes URL + headers (e.g., Accept-Language)

**4. Denormalization.**
- Pre-compute joins / aggregations into materialized views or denormalized tables
- Read = single key lookup instead of multi-table join
- Tradeoff: more storage, more write complexity, eventual consistency between source and view

**5. Search index for complex queries.**
- Elasticsearch / Solr for full-text and complex filtering
- Synced from DB via CDC
- Offloads expensive queries from primary DB

**6. Read-only replicas at edge / regional read replicas.**
- Reduces cross-region read latency
- Each region serves its local users from a local replica

**7. Sharding (last resort).**
- Only if no replication setup can handle the read volume
- Most read-scaling problems are solved by replicas + cache long before sharding is needed

**Order of operations in interviews:** cache → replicas → CDN → denormalize → search index → shard. Don't skip ahead.

**Key takeaway:** caching solves most read-scale problems. Replicas handle the rest. Sharding for reads is rarely needed if writes don't also need it.

---

## Pattern — Scaling writes

Writes are harder than reads to scale because all writes must converge to a single source of truth. Maps to: high-write workloads (logs, metrics, events, analytics).

**The toolkit:**

**1. Vertical scaling.**
- Bigger box. Modern Postgres handles 10-50k QPS writes on beefy hardware.
- Always cheaper than going distributed if it's enough.

**2. Batching.**
- Instead of 1000 individual inserts, one batch insert. 10-100× throughput.
- Tradeoff: small added latency (wait for batch fill or timeout)

**3. Async writes via queue.**
- Client writes to Kafka/SQS instantly; consumer drains into DB at sustainable rate
- Decouples burst writes from DB capacity
- Tradeoff: eventual consistency (write isn't durable in DB until consumer processes it)

**4. Write-optimized storage engine.**
- LSM-tree DBs (Cassandra, RocksDB) have much higher write throughput than B-tree DBs (Postgres)
- Tradeoff: slower reads, eventual consistency in distributed mode

**5. Sharding (the real scaling answer).**
- Split writes across N shards by key
- Each shard handles 1/N of the load
- Picking the right shard key is the whole game (see sharding topic)

**6. Event sourcing / append-only logs.**
- Writes are pure appends — no updates, no contention on hot rows
- Highest possible write throughput
- Reads computed by replaying or pre-aggregating events
- Used in: ledger systems, audit trails, analytics

**7. CRDTs (Conflict-free Replicated Data Types).**
- For multi-leader writes that must converge automatically
- Counters, sets, etc. with merge semantics that always converge
- Niche but mentionable for collaborative editing

**Common high-write patterns:**
- **Metrics ingestion:** Kafka → time-series DB (writes are appends) — handles millions of writes/sec
- **Logs:** same pattern, append-only by nature
- **Counters/likes:** Redis `INCR` first, periodic flush to DB

**Key takeaway:** batching + queuing handles bursty writes. Sharding handles sustained scale. Append-only / LSM for the highest throughput.

---

## Pattern — Handling large blobs

When the system handles large files (images, videos, documents, audio). Maps to: Dropbox, YouTube, Instagram, S3-like services.

**Core principle: don't put blobs in your database.**

**The standard architecture:**
1. Object store (S3, GCS, Azure Blob) holds the actual bytes
2. Metadata DB (Postgres / DynamoDB) holds: blob ID, owner, size, content-type, location, version
3. Client interacts with metadata DB for queries, then directly with object store for transfer

**Direct upload (presigned URLs):**
- Client requests upload from your API
- API generates presigned S3 URL (signed, short-lived, single-purpose)
- Client uploads directly to S3 — your servers never see the bytes
- Reduces bandwidth and CPU on your infra by orders of magnitude

**Downloads:**
- Same pattern: presigned download URLs, direct from S3
- Or use a CDN in front of S3 for caching at edge

**Chunked uploads (for large files):**
- Split file into chunks (5-100 MB each)
- Upload chunks in parallel; resumable on failure
- S3 multipart upload supports this natively

**Deduplication:**
- Hash the file (SHA-256); if hash already exists, skip storage and just create a metadata reference
- Saves massive amounts of storage for shared files

**Streaming (video):**
- Don't download the full file to play. Use HLS or DASH: split video into many small chunks (~6s each), client requests chunks adaptively based on bandwidth
- Pre-encode at multiple bitrates (240p, 480p, 1080p, 4K)
- CDN caches chunks near users

**Garbage collection:**
- Orphaned blobs (metadata deleted but blob remains): periodic sweep job
- S3 lifecycle policies for auto-archival to cheaper tiers (Glacier) or deletion

**Encryption:**
- At rest: server-side encryption (S3 SSE) is automatic
- In transit: HTTPS everywhere
- Sensitive content: client-side encryption with user-held keys

**Key takeaway:** metadata DB + object store + presigned URLs + CDN. This combination is the answer to almost every "large blob" question.

---

## Pattern — Managing long-running tasks

When a user request triggers work that takes longer than a synchronous HTTP timeout (30s+). Maps to: video encoding, report generation, ML inference, batch jobs, email sending.

**Don't block the request.** Return immediately with a job ID; do the work asynchronously.

**The standard architecture:**
1. API receives request → creates job record in DB (status: queued) → enqueues to message broker (SQS, RabbitMQ, Kafka) → returns 202 with job ID
2. Worker pool consumes the queue, processes jobs, updates job status in DB
3. Client polls `GET /jobs/{id}` for status, or subscribes via SSE/WebSocket for completion notification

**Job state machine:** `queued → running → (completed | failed | cancelled)`. Persist state so a worker crash doesn't lose progress.

**Retries:**
- Failed jobs retry with exponential backoff (1s, 2s, 4s, 8s, capped)
- Cap retries to avoid infinite loops
- After max retries → dead-letter queue for human inspection

**Idempotency:**
- A worker may crash mid-job and another picks it up → the job runs twice
- Make work idempotent (check "already done?" first), or use idempotency keys

**Visibility timeouts (SQS-style):**
- When a worker pulls a message, it's hidden from other workers for N seconds
- Worker must finish or extend the timeout
- If worker dies, message reappears after timeout for someone else

**Priority queues:**
- Multiple queues with different priorities; workers drain high-priority first
- Or weighted: take 80% from high-priority, 20% from low-priority

**Scaling workers:**
- Auto-scale based on queue depth: queue growing → add workers
- Bound by downstream resources (e.g., don't spawn 1000 workers if DB only handles 50 concurrent)

**Long-running task patterns by use case:**
- **Video encoding:** queue → encoder pool → write multiple bitrates to S3 → notify
- **Report generation:** queue → worker queries DB → writes to S3 → email link
- **Batch jobs:** scheduled cron → fan-out to workers → fan-in for aggregation

**Key takeaway:** queue + workers + persistent job state + idempotency + retries with backoff + DLQ. Same pattern for nearly every long-running task.

---

# Part 3 — Reliability & observability

## Failure modes — what can break and how

Datadog explicitly grades on failure handling (pitfall #5). Have a mental list of what goes wrong in distributed systems.

**Hardware/process failures:**
- Server crash (OOM, kernel panic, hardware) — handle with replication + health checks + auto-restart
- Disk failure — handle with RAID + replication + backups
- Network partition — handle per CAP theorem (degrade availability or consistency)

**Network failures:**
- Packet loss — handle with TCP retransmission (built in)
- High latency / brownouts — handle with timeouts and circuit breakers
- DNS failures — handle with retries + cached resolution

**Dependency failures:**
- Downstream service down — circuit breaker + fallback (cached response, default value)
- Slow downstream — timeout + bulkhead (limit concurrent calls so it can't drown your service)
- Cascading failures — when one service fails, retries amplify load on next layer (retry storm)

**Data failures:**
- Replication lag — read-your-writes routing
- Split-brain — consensus (Raft, Paxos) for elections
- Data corruption — checksums, regular backup verification

**Traffic failures:**
- Traffic spike — auto-scaling + load shedding (drop low-priority requests when overloaded)
- DDoS — rate limiting + WAF + CDN
- Cache failure → DB stampede — request coalescing + circuit breaker on DB

**Process-level failures:**
- Memory leak — health checks restart pods periodically
- Slow leak (file descriptors, connections) — monitoring + alerting on resource trends
- Bad deploy — canary deploys + automatic rollback on error rate spike

**Interview behavior:** when you describe a component, immediately ask "what happens if this fails?" and answer it. "If the cache goes down, requests fall through to DB; we need to make sure DB can handle the spike, so we'll add a circuit breaker."

**Key takeaway:** every component you draw, ask "what if this fails?" Replication, retries, timeouts, circuit breakers, fallbacks — pick the right one for each failure mode.

---

## Retries, timeouts, circuit breakers

The trio of resilience patterns. Mention all three when discussing service-to-service communication.

**Timeouts:**
- Every network call MUST have a timeout. No exceptions.
- Default infinite timeout = your thread pool fills up waiting → your service dies
- Pick timeouts based on p99 of the downstream + a safety margin
- Common values: 100ms-1s for fast internal calls, 5-30s for batch operations

**Retries:**
- For transient failures (timeout, 5xx, network blip)
- **Exponential backoff:** 100ms, 200ms, 400ms, 800ms... prevents retry storms
- **Jitter:** randomize backoff slightly so all retries don't sync up after a downstream recovers
- **Cap the retry count** (typically 3-5)
- **Never retry non-idempotent operations** (e.g., POST without an idempotency key) — you'll double-charge users
- **Retry only on retryable errors** (5xx, timeout). Don't retry 4xx — those won't change.

**Circuit breakers:**
- After N consecutive failures, "open" the circuit → fail fast for M seconds without even trying
- After M seconds → "half-open": let one test request through; if it succeeds, close circuit; else stay open
- Three states: closed (normal), open (failing fast), half-open (testing)
- Prevents cascading failures: if downstream is dead, don't pile thousands of waiting threads on it
- Libraries: Hystrix (legacy), resilience4j, Polly, your service mesh's built-in (Istio, Linkerd)

**Bulkheads:**
- Limit concurrent calls to a downstream so one slow dependency can't consume all your threads
- Example: 50 connection pool slots for the recommendation service; if it slows down, only 50 of your requests are stuck, the rest can continue serving

**Fallbacks:**
- When all retries fail or circuit is open: return cached value, default value, or degraded response
- Better than failing the whole user request

**Common interview phrasing:** "Each service-to-service call has a timeout, retries with exponential backoff and jitter for transient errors, and a circuit breaker so a failing dependency doesn't take down upstream callers."

**Key takeaway:** timeout + bounded retry with jitter + circuit breaker + fallback. These four together are the standard resilience pattern.

---

## Observability — the 3 pillars and 4 golden signals

Datadog grades on observability (pitfall #6). Know the vocabulary.

**The 3 pillars of observability:**
- **Metrics** — numerical time-series, aggregated. Cheap, queryable. Good for dashboards and alerts.
- **Logs** — textual events with context. Expensive at scale. Good for debugging specific requests.
- **Traces** — end-to-end request path through services (spans). Essential in microservices.

**Metric types:**
- **Counter** — monotonically increasing (request count, errors)
- **Gauge** — goes up and down (memory, queue depth, active connections)
- **Histogram / Summary** — distributions (latency percentiles)

**Cardinality is the killer.** A metric with tag `user_id` × 100M users = 100M time-series. Avoid high-cardinality tags. Bound them: HTTP status (~10 values) is fine; user IDs (millions) are not.

**The 4 golden signals (Google SRE):** for any service, monitor:
1. **Latency** — how long requests take (p50, p99)
2. **Traffic** — how much demand (QPS)
3. **Errors** — rate of failed requests (5xx, timeouts)
4. **Saturation** — how full your resources are (CPU, memory, queue depth)

**Alerting principles:**
- Alert on **symptoms** users feel (error rate, latency), NOT on causes (CPU high) — high CPU may be fine
- **SLO-based alerting:** define an SLO (e.g., 99.9% requests <500ms) → alert on error budget burn rate
- Alerts split into: **page** (wakes someone up — actionable, urgent) vs **ticket** (creates a Jira — informational)
- Avoid alert fatigue: every false positive trains people to ignore real ones

**Distributed tracing:**
- Generate a trace ID at the entry point; propagate via headers to every downstream call
- Each service emits spans with the trace ID
- Tools: OpenTelemetry (instrumentation standard), Datadog APM, Jaeger, Zipkin

**At Datadog interviews specifically:** mention Datadog APM by name when discussing observability. "I'd track API latency with Datadog APM, set up monitors on the 4 golden signals, and use distributed tracing to debug cross-service issues." This is literally an example response in their guide.

**Key takeaway:** metrics + logs + traces; 4 golden signals; alert on symptoms not causes; mention Datadog APM by name.

---

## Idempotency — the unsung hero

Idempotency means "running this operation multiple times has the same effect as running it once." Critical for retries, queues, and at-least-once delivery.

**Why it matters:**
- Networks fail. Workers crash. Messages get redelivered.
- Without idempotency, retries cause duplicates (double-charges, double-emails, inflated counters).
- "Exactly-once" delivery is mostly a myth at scale; "effectively once" via idempotent consumers is reality.

**How to make operations idempotent:**

**1. Natural idempotency.**
- `SET status = 'completed'` is idempotent (running it twice = same result)
- `INCR counter` is NOT idempotent — running twice doubles the increment
- Prefer absolute updates over relative ones when possible

**2. Idempotency keys.**
- Client generates a unique key per logical request (UUID)
- Server stores `idempotency_key → response` mapping
- Retry with same key → returns cached response, doesn't re-process
- Stripe API, Square, etc. all use this pattern

**3. Conditional updates (compare-and-set):**
- `UPDATE ... WHERE version = N` — only succeeds if version matches
- Replays of stale updates fail safely

**4. Dedup tables:**
- Track processed message IDs in a dedup table
- On message receipt: check if ID exists → skip if yes, process + insert if no
- Bloom filter front for speed when dedup table is large

**5. Idempotent message processing in queues:**
- Kafka with idempotent producers + transactional consumers gives you effectively-once semantics
- Or: design consumers to handle duplicates gracefully (idempotent business logic)

**Where to apply:**
- Payment APIs (always)
- Webhook handlers (always)
- Queue consumers (always)
- Any retry-able operation
- HTTP PUT (idempotent by HTTP spec); HTTP POST (NOT idempotent — needs idempotency key)

**Interview phrase:** "I'll require an idempotency key on the create-payment endpoint so retries from the client don't double-charge." Bring this up unprompted — it's a senior signal.

**Key takeaway:** idempotency keys for HTTP, dedup IDs for queues, conditional updates for state changes. Required for any system with retries.

---

## Rate limiting — token bucket vs sliding window

Comes up in API design, abuse prevention, and Datadog's own example list.

**Why rate limit:**
- Protect downstream services from overload
- Enforce per-user/per-tier quotas
- Prevent abuse (scrapers, brute-force, DDoS)

**Common algorithms:**

**1. Fixed window:**
- "Max 100 requests per minute per user"
- Counter resets every minute
- Simple, but allows bursts at window boundaries (200 requests in 2 seconds across boundary)

**2. Sliding window log:**
- Store timestamp of every request in a sorted set (Redis ZSET)
- On request: remove entries older than window, count remaining; allow if under limit
- Accurate but high memory (one entry per request)

**3. Sliding window counter:**
- Approximation: weighted combination of current and previous fixed windows
- Cheaper than full log, smoother than fixed window
- Standard for production rate limiting

**4. Token bucket (the most popular):**
- Bucket holds N tokens, refills at R tokens/sec
- Each request consumes 1 token; if no tokens, reject
- Allows bursts up to bucket size; sustained rate = R
- Used by AWS, Stripe, basically everyone

**5. Leaky bucket:**
- Requests enter a queue (bucket); processed at fixed rate
- Smooths bursts into a constant outflow
- Used when downstream needs steady load

**Where to enforce:**
- **Edge / API gateway** — first line of defense, blocks abuse before it hits your services
- **Per-service** — protect specific bottlenecks
- **Per-user** — quota enforcement
- **Per-IP** — DDoS mitigation (combined with WAF)

**Distributed rate limiting:**
- Single Redis instance with `INCR + EXPIRE` for the counter
- Or local rate limiters per server, with eventually-consistent global state
- Tradeoff: strict global limit (single Redis = SPOF + latency) vs approximate (local, faster, may exceed limit slightly)

**Response when limited:**
- HTTP 429 Too Many Requests
- `Retry-After` header tells client when to retry
- `X-RateLimit-*` headers tell client their current quota status

**Key takeaway:** token bucket at the API gateway with Redis-backed counters is the standard. 429 with Retry-After header for the response.

---

# Part 4 — Big-data data structures

## Bloom filters — probabilistic membership

A Bloom filter answers: "have I seen this item before?" with two possible answers:
- **"Probably yes"** (small false positive rate)
- **"Definitely no"** (zero false negatives)

**How it works:**
- A bit array of size M, all initialized to 0
- K hash functions
- Insert: hash item with each of K functions; set those K bits to 1
- Query: hash item; if all K bits are 1 → "probably yes"; if any bit is 0 → "definitely no"

**Properties:**
- Space-efficient: a few bits per item (~10 bits/item for 1% false positive rate)
- O(K) insert and query (constant — K is typically 5-10)
- Cannot delete (would risk false negatives) — use Counting Bloom filter if needed
- Cannot retrieve items, only test membership

**Classic use cases:**
- **Cache penetration prevention:** before hitting DB on cache miss, check Bloom filter — if "definitely not", return null without DB query
- **Web crawler "have I seen this URL?"** — saves billions of DB lookups
- **DB query optimization:** Cassandra and other LSM-tree DBs use Bloom filters per SSTable to avoid disk reads
- **Spam / malicious URL detection:** quick "is this URL on the blocklist?" check
- **Username availability** at signup — quick "is this taken?" with DB confirmation only on positive

**Interview pattern:** "We expect 90% of lookups to be for non-existent items. A Bloom filter at the cache layer rejects those in microseconds without touching the DB."

**Sizing:** for N items at false-positive rate p, need ~`-N × ln(p) / (ln 2)²` bits. For 1B items at 1% FP: ~9.6 bits/item = ~1.2 GB.

**Key takeaway:** Bloom filter = "definitely not OR probably yes" at tiny memory cost. Use as a cheap pre-check in front of expensive operations.

---

## HyperLogLog — counting unique items at scale

Counts distinct items in a stream using **constant memory**, regardless of stream size. Trades exactness for massive memory savings.

**The problem it solves:**
- "How many unique users visited the site today?" with 100M visitors and only 16 KB of memory
- A naive set would be ~100M × ~100 bytes = ~10 GB
- HyperLogLog gives ~99% accurate count in ~12 KB

**How it works (high level):**
- Hash each incoming item
- Look at the leading zeros in the binary hash
- Track the maximum number of leading zeros seen across hash buckets
- Use that to estimate cardinality (more leading zeros = larger set)
- Multiple "registers" (buckets) for variance reduction

**Properties:**
- **Constant memory** (typically 12 KB for ~1% error)
- **Mergeable**: HLL(A) + HLL(B) = HLL(A ∪ B). Critical for distributed counting — each shard maintains its own HLL, merge for global count
- O(1) insert, O(1) merge
- Accuracy ~0.5-2% standard error

**Classic use cases:**
- **Unique visitors** per day/hour
- **Distinct queries** in analytics
- **Cardinality of monitoring metrics** (Datadog uses HLL-style structures for unique counts in metric tags)
- **Approximate count-distinct** in OLAP databases (Redshift, Druid, ClickHouse all support it)

**Redis support:** native commands `PFADD`, `PFCOUNT`, `PFMERGE`. Mention this when an interviewer asks about counting uniques.

**When NOT to use:**
- When you need exact counts (financial, regulatory)
- When you need to retrieve the items, not just count them (use a set)

**Key takeaway:** HyperLogLog = approximate distinct count in constant memory, mergeable across shards. Default answer for "count unique X at scale."

---

## Count-min sketch — frequency estimation

Counts how many times each item appears in a stream, in sublinear memory. Always overestimates (never undercounts).

**The problem it solves:**
- "How many times has hashtag #X been used today?" across millions of hashtags and billions of uses
- Exact counts = one counter per hashtag = potentially massive memory
- Count-min sketch gives approximate counts in fixed memory

**How it works:**
- 2D array of counters: D rows × W columns
- D hash functions (one per row)
- Insert: for each of D hash functions, increment the corresponding column in that row
- Query: hash item with each of D functions; return the **minimum** of those D counter values

The minimum is taken because hash collisions can only inflate counters, never deflate them — so the minimum is closest to the truth.

**Properties:**
- **Constant memory** regardless of stream size
- **Always overestimates** (never undercounts)
- O(D) insert and query
- Mergeable across shards (sum the matrices)
- Tunable: more rows/columns = more accuracy, more memory

**Classic use cases:**
- **Heavy hitters / top-K:** find the most frequent items in a stream (combined with a min-heap of candidates)
- **Trending topics:** counting hashtag/keyword frequency in real time
- **Network monitoring:** per-IP packet counts
- **Database query optimization:** track which values appear most often

**Comparison to alternatives:**
- vs exact hash map: count-min sketch uses constant memory but is approximate
- vs Bloom filter: Bloom filter answers "have I seen?" (boolean); count-min answers "how many times?" (integer)
- vs HyperLogLog: HLL counts uniques across the stream; count-min counts occurrences per item

**Interview pattern:** "For top-K trending hashtags from a billion-event/day stream, I'd use count-min sketch in each ingest worker, merge periodically, and maintain a min-heap of the top K candidates."

**Key takeaway:** count-min sketch = approximate per-item frequency in constant memory. The default for top-K and frequency questions at scale.

---

# Part 5 — Final prep

## Pre-interview checklist (the morning of)

Use this 10 minutes before the interview. Don't try to learn anything new.

**Setup:**
- Excalidraw open in a tab (Datadog's preferred whiteboard tool — practice with it beforehand)
- A blank document or notepad for jotting requirements
- Water, quiet space, working camera/mic

**Mental warmup (5 min):**
- Run through S.O.L.I.D. out loud: Scope → Outline → List → Identify scaling → Discuss monitoring
- Recite the 8 pitfalls once
- Think about your 30-second elevator pitch on each: caching, sharding, replication, queues

**The 5-question opening (your script for the first 5 minutes):**
1. "What's the primary user action?" (functional req)
2. "Read-heavy or write-heavy?"
3. "What's the scale — DAU and rough QPS?"
4. "What's the latency budget — p99?"
5. "Strong consistency anywhere, or is eventual OK?"

**Reminders to keep front-of-mind:**
- Narrate before drawing
- Justify every storage choice
- Surface tradeoffs unprompted
- Mention monitoring before being asked
- Mention Datadog APM by name when discussing observability
- It's OK to say "let me think for a moment"

**Body language / tone:**
- Excited about the problem, not anxious
- Treat the interviewer as a teammate solving the problem with you, not an examiner
- Pause and ask "does this approach make sense before I go deeper?" — this is a senior habit

**Key takeaway:** the morning of, don't cram new content. Run the framework, breathe, and trust your prep.

---

## The "I don't know" playbook

You will hit a question you don't fully know. How you handle it is the test, not the gap.

**Don't bluff.** Interviewers smell it instantly. Bluffing is the fastest way to fail.

**The 3-step recovery:**

**1. Acknowledge directly.** "I haven't worked with X directly."

**2. Generalize from what you know.** "But it sounds similar to Y, which I have used. With Y we'd handle this by Z, and I'd guess the same principle applies here."

**3. Name what you'd consult.** "In a real situation I'd check the docs and talk to someone who's used it; for now I'll work with that approximation."

**Concrete examples:**

*"How does Cassandra handle X?"* → "I haven't deployed Cassandra in production. I know it's an LSM-tree store with leaderless replication and tunable consistency. For X specifically, I'd guess [reasoning from those properties], but I'd verify."

*"What's the consensus algorithm in etcd?"* → "etcd uses Raft. I know Raft at the level of leader election + log replication; I haven't implemented it. The key property here is [strong consistency / availability tradeoff]."

*"How would you implement exactly-once delivery in Kafka?"* → "Effectively-once is the realistic goal — I'd use idempotent producers and transactional consumers, plus idempotency keys in business logic. True exactly-once is debated and usually approximated."

**When the gap is bigger:** "I genuinely don't know this area well. Could we shift to [a related area I do know]?" — interviewers respect this. Almost no one knows everything.

**Key takeaway:** authentic uncertainty + structured reasoning > confident bluffing every time. Datadog explicitly values reasoning over knowledge of specific technologies.

---

## Mock practice prompts (use HelloInterview videos as the answer key)

Use these for self-practice. 50-min timer, Excalidraw, talk out loud. Then watch the corresponding HelloInterview video to compare.

**Vanilla FAANG questions (Datadog's official suggestions):**
1. **URL shortener (bit.ly clone)** — focus: hash collisions, DB choice, caching, base62 encoding. *HelloInterview: Bitly walkthrough.*
2. **Messaging system (WhatsApp)** — focus: WebSockets, message ordering, group chats, online presence. *HelloInterview: WhatsApp walkthrough.*
3. **Rate limiter** — focus: token bucket, distributed Redis, per-user quotas. *HelloInterview: Distributed Rate Limiter walkthrough.*
4. **File storage (Dropbox)** — focus: chunking, dedup, sync protocol, large blobs pattern. *HelloInterview: Dropbox walkthrough.*
5. **Video streaming (YouTube)** — focus: encoding pipeline, CDN, adaptive bitrate. *HelloInterview: YouTube walkthrough.*
6. **News feed (FB)** — focus: fanout-on-write vs fanout-on-read, ranking, hybrid. *HelloInterview: FB News Feed walkthrough.*

**Datadog-flavored (in case you get one):**
7. **Top K trending items (YouTube most-watched)** — focus: count-min sketch, heap, time windows. *HelloInterview: YouTube Top K walkthrough.*
8. **Ad click aggregator** — focus: high-write ingestion, idempotency, near-real-time aggregation. *HelloInterview: Ad Click Aggregator walkthrough.*
9. **Web crawler** — focus: BFS at scale, dedup with Bloom filters, politeness, frontier. *HelloInterview: Web Crawler walkthrough.*

**Practice rhythm:**
- Day 1-2: Watch a HelloInterview case study video, take notes
- Day 3-4: Attempt the same problem with a 50-min timer BEFORE watching; compare to video
- Day 5+: Attempt new problems cold, watch video as the answer key

**Self-evaluation rubric (after each mock):**
- Did I do all 5 S.O.L.I.D. steps?
- Did I justify every storage choice with a property?
- Did I surface tradeoffs unprompted at least 3 times?
- Did I mention failure handling for at least 3 components?
- Did I mention monitoring before being asked?
- Did I keep moving (not stuck on one detail)?

**Key takeaway:** 1 mock per day for the next 7 days, with HelloInterview as your answer key. The talking out loud is the part that matters — don't skip it.
