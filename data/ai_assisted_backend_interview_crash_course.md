# AI-Assisted Backend Interview — Crash Course

> Personal prep notes for the warehouse-fronting service interview.
> Six concerns, all flowing from one fact: warehouse queries are **slow, expensive, and produce big results**.

---

## Layer 0: SQL vs NoSQL — quick correction

**SQL is not about "sequential" data** — it's about *tabular* data (rows and columns with a fixed schema). A SQL table is an unordered set of rows; you only get order when you ask for it with `ORDER BY`. The "S" stands for *Structured*, not Sequential.

**NoSQL** is an umbrella for "anything that isn't a traditional relational database":

- **Key-value stores** (Redis, DynamoDB)
- **Document stores** (MongoDB) — JSON blobs indexed by key
- **Wide-column** (Cassandra) — sparse, distributed tables
- **Graph databases** (Neo4j) — nodes and edges

**The real distinction:** SQL = tables with rigid schemas + a powerful query language for joining/filtering across them. NoSQL = various other data models, usually trading query flexibility for horizontal scale or simpler access patterns.

For this interview you don't need to be a database person. You need to understand **one specific thing** very well: what a *data warehouse* is, and what its Python SDK gives you.

---

## Layer 1: What a data warehouse is and why this interview is about one

A **data warehouse** is a database optimized for analytics, not for transactional workloads. Examples: **Snowflake**, **BigQuery**, **Redshift**, **Databricks**. The interview is almost certainly built around one of these (Snowflake is the most likely).

### Key differences from a regular database (Postgres, MySQL)

- **Storage is separated from compute.** Your data lives in cheap object storage (S3-style); when you run a query, the warehouse spins up CPUs to read that storage and compute the answer. You pay per second of compute.
- **Queries can be slow.** A typical query scans gigabytes-to-terabytes. "Slow" here means seconds to minutes, sometimes longer.
- **Queries are expensive.** Re-running a 30-second query that scanned 100GB costs real money, every time.
- **Result sets can be huge.** A query can return millions or billions of rows.

These three properties — slow, expensive, potentially huge results — are the entire reason this interview exists.

### Every design topic in the prep doc flows from these properties

| Property | Design consequence | Doc section |
|---|---|---|
| Queries are slow | Can't make user wait synchronously → async jobs | Async Job-Style Design |
| Queries are expensive | Don't re-run for pagination → result handles | Confirming Queries Are Not Re-run |
| Results can be huge | Don't load all into memory → streaming pagination | Pagination and Large Result Sets |
| Async jobs outlive a process | State must be durable → crash recovery | Surviving Worker Crashes |
| Service exposes raw SQL | Untrusted input you can't sanitize like params → role-level defense | SQL Injection and Query Safety |
| Multi-tenant warehouse access | Each tenant has own credentials → secrets manager | Secure Credential Storage |

Once you see that all six topics are downstream consequences of "warehouses are slow, expensive, and produce big results," the document stops looking like a checklist and starts looking like one coherent design conversation.

---

## Layer 2: Synchronous vs asynchronous — the foundational pattern

### Synchronous (the wrong design here)

```
client → POST /query {sql: "SELECT ..."}
         (waits 90 seconds, holding the HTTP connection open)
client ← {results: [...]}
```

Why it's wrong:

- HTTP timeouts (load balancers, proxies, browsers) typically kick in around 30–60 seconds. You'll lose connections.
- The client thread is blocked the whole time.
- If anything fails mid-query, the client doesn't know what state things are in.
- You can't show the user progress.

### Asynchronous (the right design)

```
client → POST /queries {sql: "SELECT ..."}
client ← {query_id: "abc123", status: "RUNNING"}     [returns immediately]

client → GET /queries/abc123                          [poll for status]
client ← {query_id: "abc123", status: "RUNNING"}

... time passes ...

client → GET /queries/abc123
client ← {query_id: "abc123", status: "SUCCEEDED"}

client → GET /queries/abc123/results?page=0
client ← {rows: [...first 1000 rows...], next_page: 1}

client → GET /queries/abc123/results?page=1
client ← {rows: [...next 1000 rows...], next_page: 2}
```

Three concerns, three endpoints:

1. **Submit** — kicks off the query, returns an ID instantly
2. **Status** — check whether it's done
3. **Results** — fetch results in pages, only after status is `SUCCEEDED`

This is the **async job pattern**, and it's everywhere in backend engineering: video transcoding services, ML training jobs, data exports, payment processing.

### What this looks like in the Snowflake SDK

```python
cur = conn.cursor()
cur.execute_async("SELECT ...")            # returns immediately
query_id = cur.sfqid                        # save this

# later, possibly in a different process:
while conn.is_still_running(conn.get_query_status(query_id)):
    time.sleep(1)

# fetch results using the saved ID, NOT the original SQL:
cur.get_results_from_sfqid(query_id)
for row in cur:
    ...
```

The crucial line is `get_results_from_sfqid` — it fetches results by *query ID*, never re-running the SQL. This is the answer to two of the six interview topics.

---

## Layer 3: How a database query actually executes

You don't need deep DB internals, but you need to understand the lifecycle well enough to defend the design.

When you submit a SQL query to a warehouse:

1. **Parse** — SQL string is parsed into an abstract syntax tree (AST). Syntax errors fail here.
2. **Plan** — the query planner decides *how* to execute: which tables to scan, in what order, which indexes to use, how to do joins. Output is an execution plan.
3. **Execute** — the plan runs. Data is read from storage, transformed, joined, aggregated. **This is the slow, expensive part.**
4. **Materialize** — the final result set is stored somewhere (the warehouse's own scratch storage), keyed by the query ID.
5. **Stream to client** — when you call "fetch results," the SDK streams chunks from the materialized result back to your process, in batches.

**Steps 1–4 happen once. Step 5 can happen many times** — each call to "fetch the next page" is just reading more rows from the already-materialized result. This is why result-handle pagination is cheap: you ran the query once, you're paging over the cached output.

The result set has a TTL on the server (Snowflake: 24 hours by default). After that, asking for more results returns an error and you have to re-run the query.

### Answer to "Confirming Queries Are Not Re-run"

> "Once the query finishes, the warehouse holds the materialized result keyed by the query ID. The SDK's `get_results_from_sfqid` reads from that cache. We never re-submit the SQL. If the result has expired from the cache, we'd have to re-run, which is why for very long-lived pagination we'd want to materialize results into our own storage."

---

## Layer 4: Pagination strategies, ranked from worst to best

### Approach A: `LIMIT/OFFSET` re-running the SQL — wrong

```python
def get_page(sql, page, page_size=1000):
    paginated_sql = f"{sql} LIMIT {page_size} OFFSET {page * page_size}"
    return execute_query(paginated_sql)   # runs the WHOLE query again, every page
```

Why it's wrong:

- **Cost**: every page re-runs the full query. 100 pages = 100x the compute cost.
- **Correctness**: if underlying data changes between page 1 and page 2, page 2 might have rows that "should have been" on page 1. Or duplicates. Or missing rows.
- **`OFFSET` is slow on its own**: even within one query, `OFFSET 1000000` makes the database compute and discard the first million rows.

### Approach B: keyset pagination — clever, but doesn't apply here

```sql
SELECT * FROM users WHERE id > $last_seen_id ORDER BY id LIMIT 1000;
```

Track the last ID you saw, ask for "the next 1000 after that." Stable, fast, no `OFFSET`. This is the right answer for **paginating an API over a known table**, but it doesn't work here because:

- We're paginating over the **result of arbitrary user SQL**, not a known table
- We can't safely modify the user's SQL to add a `WHERE id > X ORDER BY id` clause

Mention this in the discussion only if asked about other contexts. Shows you know it exists.

### Approach C: result-handle pagination — correct

The query runs once and materializes a result. We page over the materialized result using a server-side cursor:

```python
# submit phase
cur.execute_async(user_sql)
query_id = cur.sfqid
save_to_durable_store(query_id, status="RUNNING")

# fetch phase, on a later request:
cur.get_results_from_sfqid(query_id)
cur.scroll(page * page_size)              # skip to offset in materialized result
rows = cur.fetchmany(page_size)
return rows
```

Properties:

- **Cheap** — each page fetch is just streaming bytes from the already-computed result. No re-execution.
- **Stable** — the result is frozen at query completion. No drift.
- **Bounded by TTL** — the result expires (24h on Snowflake). For longer-lived pagination, persist results yourself (write to S3 in chunks, paginate over those).

### Discussion points the interviewer wants

- Result handles have a TTL — explain how you'd handle expiry
- `scroll(N)` on huge offsets is still O(N) on the server side; for forward-only streaming, just keep fetching without seeking
- For truly huge results (billions of rows), the right answer might be **"export to S3/object storage as Parquet, give the user a presigned URL"** rather than paginating through your service at all. Mention this — strong signal.

---

## Layer 5: Durability and crash recovery

The danger:

```
Worker A: receives submit_query request
        : calls cur.execute_async(sql) → query_id = "abc123"
        : query is now running on the warehouse, costing money
        : Worker A keeps query_id only in a Python dict
        : Worker A crashes (OOM kill, deploy, bug, host reboot)

Result: query is still running on the warehouse (or has finished and is cached).
        Nobody knows the query_id.
        The warehouse will eventually time out and discard the result.
        The user gets nothing. The compute was wasted.
```

### The fix: persist-then-acknowledge

Persist the query ID to durable storage **before** you tell the client about it.

```python
def submit_query(tenant, sql):
    # 1. Submit to warehouse — returns immediately with a query ID
    cur = get_connection(tenant).cursor()
    cur.execute_async(sql)
    query_id = cur.sfqid

    # 2. CRITICAL: persist before returning to client
    db.execute("""
        INSERT INTO queries (query_id, tenant, sql, status, created_at)
        VALUES (?, ?, ?, 'RUNNING', NOW())
    """, [query_id, tenant, sql])

    # 3. Now safe to return — even if we crash here, recovery is possible
    return {"query_id": query_id}
```

A separate process (or any worker) can do recovery:

```python
def poll_running_queries():
    rows = db.execute("SELECT query_id, tenant FROM queries WHERE status='RUNNING'")
    for row in rows:
        conn = get_connection(row.tenant)
        status = conn.get_query_status(row.query_id)
        db.execute("UPDATE queries SET status=?, last_polled_at=NOW() WHERE query_id=?",
                   [status, row.query_id])
```

**This decouples submission from polling.** Any worker can poll any query. If the submitting worker dies, another worker picks up where it left off.

### The subtle nuance worth mentioning

The persist must come **after** the SDK call (we don't have a query_id until SDK gives us one). So there's a small window where the warehouse has accepted the query but you haven't persisted it yet. Crash in that window = leaked orphan query. Mitigations:

- Make the window small (no other work between SDK call and DB write)
- The orphan eventually expires on the warehouse side (bounded waste, not unbounded)
- For stronger guarantees, use a pattern like "reserve a query_id locally first, pass it to the warehouse" — but most SDKs don't allow client-supplied IDs, so you live with the small window

This kind of nuanced trade-off discussion scores points. The interviewer doesn't want a perfect answer; they want to see you reason about *where the cracks are* in your design.

---

## Layer 6: SQL safety when the API accepts SQL

You have a service whose API is *literally* "send me SQL, I'll run it." Standard advice ("use parameterized queries") doesn't apply — there are no parameters, the whole input is SQL.

**The correct framing: defense at the database role/connection layer, not the string layer.**

Your service connects using a database role (a user account inside the database). That role has *grants* — permissions to do specific things.

### The defenses, in order of importance

1. **The role has only `SELECT` grants on permitted schemas.** Even if a user submits `DROP TABLE users`, the warehouse rejects it: "permission denied." The application doesn't have to detect malicious SQL — the database does.

2. **Disable multi-statement execution.** Snowflake setting: `MULTI_STATEMENT_COUNT=1`. Without this, someone could submit `SELECT 1; DROP TABLE users;`.

3. **Per-tenant roles.** Tenant A's queries run under role `tenant_a_readonly`, which has grants only on tenant A's schema. Tenant B literally cannot read tenant A's data because the *database* enforces it. Much stronger than application-level filtering.

4. **Resource limits.** Set query timeout (`STATEMENT_TIMEOUT_IN_SECONDS`) and per-warehouse credit limit. Even a benign query that accidentally cross-joins two billion-row tables can't run for 6 hours and bankrupt you.

5. **SQL parsing as defense in depth.** Use `sqlglot` to parse incoming SQL, walk the AST, reject anything that isn't a `SELECT` (or `WITH ... SELECT`). Catches accidents, gives better error messages. Additional, not primary defense.

### The framing that scores

> "You can't sanitize raw SQL the way you sanitize parameters — that's a losing game. The defense has to be at the boundary: a least-privilege DB role per tenant, single-statement execution, and resource governance. Parsing the SQL is defense in depth."

---

## Layer 7: Multi-tenant credentials

Each tenant has their own warehouse account. Where do those credentials live?

### Wrong: environment variables

`TENANT_ACME_PASSWORD`, `TENANT_FOO_PASSWORD`... This is what the prep doc calls "per-customer environment-variable sprawl." Doesn't scale, not auditable, rotation = redeploy.

### Right: a secrets manager

HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager.

The pattern:

- Secrets stored keyed by tenant: `secrets/tenants/acme/snowflake_credentials`
- Service authenticates to secrets manager using its **own** identity (e.g. an IAM role)
- At request time, service looks up authenticated tenant, fetches credentials, opens connection, runs query
- Credentials cached in memory for short TTL (e.g. 5 min) to avoid hammering the secrets manager
- Rotation: update secret in manager → cache expires → new connections use new credentials. **No deploy needed.**

### Bonus points

- **Key-pair authentication instead of passwords.** Snowflake (and most warehouses) support RSA key-pair auth. The private key lives in your secrets manager and signs JWTs locally — no password ever crosses the wire. Network compromise doesn't compromise the credential.
- **Audit logging.** Every credential fetch is logged: who, when, why. If someone exfiltrates credentials, you have a paper trail.
- **Least-privilege IAM for the service itself.** The service can read tenant secrets but not write or delete them. Separation of duties.

---

## The complete mental model

```
                        ┌─────────────────────┐
                        │   Secrets Manager   │
                        │  (per-tenant creds) │
                        └──────────┬──────────┘
                                   │ fetch creds at request time
                                   ▼
client ──HTTP──▶  ┌─────────────────────────────┐
                  │      Your Service           │
                  │                             │
                  │  POST /queries     ───────┐ │
                  │  GET  /queries/:id        │ │
                  │  GET  /queries/:id/results│ │
                  └─────────────────┬─────────┘ │
                                    │           │
                                    │  persist  │ submit/poll/fetch
                                    ▼           ▼
                       ┌─────────────────┐  ┌──────────────┐
                       │ Durable Store   │  │  Warehouse   │
                       │ (Postgres/etc)  │  │  (Snowflake) │
                       │                 │  │              │
                       │ queries table:  │  │  - parses    │
                       │  query_id       │  │  - plans     │
                       │  tenant         │  │  - executes  │
                       │  status         │  │  - caches    │
                       │  created_at     │  │    results   │
                       │  ...            │  │    by ID     │
                       └─────────────────┘  └──────────────┘
```

### Six concerns, all from "warehouses are slow, expensive, big results"

1. **Async** because slow → submit/status/results, not one big call
2. **Result-handle pagination** because expensive → never re-run for paging
3. **Streaming** because results are big → don't load all in memory
4. **Durable state** because async outlives a process → persist before ack
5. **Role-based SQL safety** because we can't sanitize SQL → least-privilege at the DB boundary
6. **Secrets manager** because multi-tenant credentials → no env var sprawl

If you can speak each of these in your own words, with the trade-offs at the edges, you're in great shape.

---

## AI workflow during the interview

1. **First five minutes — no AI.** Read the prompt, restate it, ask clarifying questions about scope. ("Should this be a real HTTP server or just two functions? Single-tenant first or multi-tenant from the start?") This is independence signal.

2. **Next five minutes — design out loud, no code yet.** "I'm going to have two endpoints. `submit` will store the query ID in a SQLite/in-memory dict for now, and we can discuss durable storage in production. `get_results` will use the result handle from the SDK to avoid re-running the query." If they nod, you're aligned.

3. **Now bring AI in for SDK boilerplate.** "Show me how to call Snowflake's Python connector to execute a query asynchronously and retrieve results by query ID." This is exactly what AI is *better* than memory for.

4. **Hand-write the orchestration logic** (storing of state, request flow), AI-assist the boilerplate (HTTP framework setup, SDK calls, error handling). Orchestration = where they're judging your understanding; boilerplate = where AI saves you 20 minutes.

5. **When something breaks, paste the actual error to the AI.** Don't describe — paste. The prep doc calls this out as a positive signal.

6. **Narrate every non-obvious choice.** Examples:
   - "I'm choosing async execution because the query might take minutes to complete."
   - "I'm storing the query ID in this dict for now, but in production this would be a Postgres row so we can recover from worker crashes."
   - "I wouldn't re-run the original SQL for pagination — I'd paginate over the result handle."

---

## What to do before the interview

In rough order of value:

1. **Sign up for a Snowflake trial.** Run three queries. Use `execute_async`. Save the `sfqid`. In a separate Python session, instantiate a new connection and call `get_results_from_sfqid` with the saved ID. Watch it work. **This single hour of hands-on will make every discussion topic real instead of abstract.**

2. **Read the Snowflake Python connector docs**, specifically the sections on async queries and `get_query_status`. Don't memorize — just see what the API surface looks like so you're not surprised.

3. **Practice narrating.** The prep doc is explicit that talking through trade-offs is a graded dimension. Even when prepping solo, narrate as if someone's listening.

4. **Mock interview** — given the spec, practice driving the AI as a senior would. Plan first, prompt for skeletons, read what's generated, push back on bad choices, narrate constantly.

---

*Six concerns, one root cause: warehouses are slow, expensive, and produce big results. Everything else follows.*
