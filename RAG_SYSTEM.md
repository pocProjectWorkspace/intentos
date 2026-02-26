# IntentOS RAG System
### *How IntentOS Understands Your World*

---

## Overview

IntentOS's RAG (Retrieval-Augmented Generation) system is the layer that gives the Intent Kernel memory and context. Without it, every task starts from zero — the user must always be fully explicit about what they want and where things are. With it, IntentOS understands the user's file world, their history, and their intent — turning vague instructions into precise actions.

> *"That report I was working on last week"* → finds it
> *"The invoice from Ahmed"* → finds it, even if it's named invoice_2024_final_v3.pdf
> *"Same thing I did with those photos last time"* → recalls the task, replays it

This is not search. This is contextual understanding of a person's digital life.

---

## The Three Indexes

IntentOS RAG maintains three separate vector indexes. Each serves a different kind of context retrieval. They are queried in combination on every task.

```
┌─────────────────────────────────────────────────────────────┐
│                     RAG SYSTEM                               │
│                                                              │
│  ┌──────────────────┐ ┌─────────────────┐ ┌──────────────┐ │
│  │   FILE INDEX     │ │   TASK INDEX    │ │ USER PROFILE │ │
│  │                  │ │                 │ │    INDEX     │ │
│  │ What exists on   │ │ What the user   │ │ Who the user │ │
│  │ the filesystem   │ │ has done before │ │ is and how   │ │
│  │ and what's in it │ │                 │ │ they work    │ │
│  └──────────────────┘ └─────────────────┘ └──────────────┘ │
│           │                   │                   │          │
│           └───────────────────┴───────────────────┘          │
│                               │                              │
│                    CONTEXT ASSEMBLER                         │
│          (merges retrieved context for Intent Kernel)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Index 1: File Index

The File Index is IntentOS's understanding of the user's filesystem. It knows what files exist, where they are, what they contain, and how they relate to each other — without the user ever having to explain their folder structure.

### What gets indexed

Every file on the user's machine is indexed, but not all files equally:

| File type | What gets stored |
|---|---|
| Documents (PDF, DOCX, TXT, MD) | Full text content, chunked |
| Images (JPG, PNG, etc.) | Filename, EXIF metadata, AI-generated caption |
| Audio/Video | Filename, duration, metadata, auto-transcript if short |
| Spreadsheets | Sheet names, column headers, first 100 rows |
| Code files | Filename, language, function/class names, comments |
| Archives (ZIP, TAR) | Filename, list of contents |
| Everything else | Filename, path, size, dates, MIME type |

### Index entry structure

```json
{
  "id": "uuid",
  "path": "/home/user/Documents/Projects/ahmed_invoice_march.pdf",
  "filename": "ahmed_invoice_march.pdf",
  "type": "pdf",
  "size_bytes": 84221,
  "created": "2024-03-14T09:23:00Z",
  "modified": "2024-03-14T09:23:00Z",
  "last_accessed": "2024-03-15T14:00:00Z",
  "content_chunks": [
    "Invoice #2024-089. Issued by Ahmed Al Rashidi...",
    "Total amount due: AED 12,500. Payment due April 14..."
  ],
  "semantic_tags": ["invoice", "payment", "Ahmed", "March 2024"],
  "embedding": [0.023, -0.441, ...],
  "thumbnail_path": "/intentos/cache/thumbs/ahmed_invoice_march.jpg"
}
```

### Indexing strategy

**Not everything is indexed at once.** Full indexing of a large filesystem on first run would be slow and intrusive. IntentOS uses a priority-based indexing schedule:

```
Priority 1 (indexed immediately on first launch):
  ─ Desktop
  ─ Documents
  ─ Downloads
  ─ Recent files (accessed in last 30 days)

Priority 2 (indexed in background over first 24 hours):
  ─ Home folder subfolders
  ─ Pictures
  ─ Music
  ─ Videos

Priority 3 (indexed opportunistically when machine is idle):
  ─ Everything else
  ─ External drives when connected

Never indexed:
  ─ System directories (/etc, /sys, /proc, C:\Windows)
  ─ Hidden config directories (.git, .ssh, .env files)
  ─ node_modules, __pycache__, build artifacts
  ─ Files the user has explicitly excluded
```

### Live index updates

The File Index stays current through a lightweight filesystem watcher (using `watchdog` on Linux/Mac, `ReadDirectoryChangesW` on Windows). When files are created, modified, moved, or deleted, the index updates within seconds. No manual re-indexing. The user never thinks about this.

```
File event detected
        │
        ├── CREATE → extract content → embed → add to index
        ├── MODIFY → re-extract → re-embed → update entry
        ├── MOVE   → update path only (no re-embedding needed)
        └── DELETE → remove from index
```

---

## Index 2: Task Index

The Task Index is IntentOS's memory of what the user has done. Every completed task is stored with its full context — the original instruction, what agents ran, what files were touched, and what the result was. This enables the system to understand references like *"same thing as last time"* and to get smarter about how a specific user prefers things done.

### Task entry structure

```json
{
  "id": "uuid",
  "timestamp": "2024-03-20T11:15:00Z",
  "raw_input": "rename all the photos from my Dubai trip by date",
  "resolved_intent": "file.batch_rename",
  "agents_used": ["file_agent", "image_agent"],
  "files_affected": [
    "/home/user/Pictures/Dubai/IMG_4821.jpg",
    "/home/user/Pictures/Dubai/IMG_4822.jpg"
  ],
  "parameters_used": {
    "rename_pattern": "YYYY-MM-DD_HH-MM_{{index}}",
    "source_metadata": "exif_date"
  },
  "result": "success",
  "duration_ms": 3200,
  "user_feedback": null,
  "embedding": [0.011, -0.233, ...]
}
```

### What the Task Index enables

**Replay:** *"Do that thing again with the new batch of photos"* — the system retrieves the most relevant past task and re-runs it with the new target.

**Pattern learning:** If the user always renames photos by date, always saves invoices to a specific folder, always exports documents as PDF — the system learns these preferences and applies them automatically without being asked.

**Disambiguation:** *"That spreadsheet I was working on"* — the Task Index knows which files the user has interacted with recently and surfaces the most likely match.

**Explanation:** *"What did you do to my Downloads folder yesterday?"* — the system can reconstruct a plain-language log of every action taken.

---

## Index 3: User Profile Index

The User Profile Index is a lightweight, structured store of inferred preferences. It is not a vector index like the others — it is a structured JSON document that is updated passively as the user works, and injected into the Intent Kernel as context on every task.

### Profile structure

```json
{
  "preferences": {
    "date_format": "YYYY-MM-DD",
    "default_export_format": "pdf",
    "preferred_image_format": "jpg",
    "preferred_archive_format": "zip",
    "language": "en",
    "timezone": "Asia/Dubai"
  },
  "frequent_folders": {
    "documents": "/home/user/Documents/Work",
    "invoices": "/home/user/Documents/Finance/Invoices",
    "photos": "/home/user/Pictures"
  },
  "frequent_contacts": [
    { "name": "Ahmed", "context": "invoices, payments" },
    { "name": "Sara", "context": "project documents" }
  ],
  "task_patterns": [
    {
      "pattern": "photo_rename",
      "frequency": 8,
      "last_used": "2024-03-20",
      "preferred_params": { "rename_pattern": "YYYY-MM-DD_HH-MM" }
    }
  ],
  "avoided_actions": [
    "permanent_delete"
  ]
}
```

This profile is never sent to any external service. It lives locally. It is used only to make the Intent Kernel's decisions more accurate for this specific user.

---

## The Context Assembler

Every time a task arrives at the Intent Kernel, the Context Assembler runs first. It queries all three indexes and packages the most relevant context into a structured block that is prepended to the kernel's prompt.

### Assembler flow

```
User input: "find the invoice from Ahmed last month"
                │
                ▼
        Query File Index
        ─────────────────
        search: "invoice Ahmed"
        filter: modified_after = 30 days ago
        returns: top 3 matching files with paths and snippets
                │
                ▼
        Query Task Index
        ─────────────────
        search: "invoice Ahmed retrieve"
        returns: last 2 similar tasks, parameters used
                │
                ▼
        Read User Profile
        ─────────────────
        frequent_folders.invoices = "/home/user/Documents/Finance/Invoices"
        frequent_contacts: Ahmed → invoices, payments
                │
                ▼
        Assembled context block:
        ──────────────────────────────────────────────────────
        Relevant files found:
          - /home/user/Documents/Finance/Invoices/ahmed_march_2024.pdf
            (modified 2024-03-14, contains: "Invoice #2024-089, Ahmed Al Rashidi, AED 12,500")
          - /home/user/Downloads/invoice_ahmed_feb.pdf
            (modified 2024-02-10)

        Recent similar tasks:
          - 2024-03-01: "open Ahmed's invoice" → opened ahmed_feb_2024.pdf

        User profile context:
          - invoices usually in: /home/user/Documents/Finance/Invoices
          - Ahmed associated with: invoices, payments
        ──────────────────────────────────────────────────────
                │
                ▼
        Intent Kernel receives context + user input
        → resolves to specific file path with high confidence
        → no clarifying question needed
```

Without RAG, the Intent Kernel would have to ask: *"I'm not sure which invoice you mean — can you give me more details?"*

With RAG, it already knows.

### Context token budget

The Context Assembler is aware of the token limits of the active inference model and manages context accordingly. It prioritises context in this order if truncation is needed:

1. Directly matching file results (always included)
2. User profile preferences (always included, small)
3. Recent similar task history (included if budget allows)
4. Older task history (dropped first if budget tight)

---

## Chunking Strategy

For document content, IntentOS uses a **semantic chunking** approach rather than fixed-size chunking. This produces more coherent retrieval results.

```
Document arrives
        │
        ▼
Split into semantic units:
  ─ Paragraphs for prose documents
  ─ Sections for structured documents (headers as boundaries)
  ─ Rows/groups for spreadsheets
  ─ Functions/classes for code files
        │
        ▼
Each chunk gets:
  ─ Its own embedding
  ─ A reference back to parent document
  ─ Its position in the document (for reconstruction)
  ─ A brief auto-generated summary (for large chunks)
        │
        ▼
Stored in vector database with metadata
```

**Chunk size targets:** 200-500 tokens per chunk for prose, with 50-token overlap between adjacent chunks to preserve context across boundaries.

---

## Embedding Model

IntentOS uses a dedicated local embedding model — separate from the inference model used by the Intent Kernel. This keeps embedding fast and cheap regardless of which inference mode the user has chosen.

**Default embedding model:** `nomic-embed-text` via Ollama (~270MB)

Why nomic-embed-text: it runs entirely locally, produces high-quality embeddings for English and multilingual text, is fast enough for real-time indexing on a CPU, and integrates trivially with the existing Ollama installation.

The embedding model is pulled automatically during first-launch setup alongside the inference model. The user never sees or configures it.

---

## Vector Database

**Default:** ChromaDB (embedded, no server required)

ChromaDB runs as an embedded library inside IntentOS — no separate database process, no port conflicts, no configuration. It stores all three indexes in a local directory (`~/.intentos/rag/`) and handles similarity search with sub-100ms latency for typical home filesystem sizes.

**Storage location:**
```
~/.intentos/
├── rag/
│   ├── file_index/          ← ChromaDB collection
│   ├── task_index/          ← ChromaDB collection
│   └── user_profile.json    ← structured JSON
├── cache/
│   └── thumbs/              ← file thumbnails
└── logs/
    └── task_history.jsonl   ← append-only task log
```

**Scaling:** For users with very large filesystems (500k+ files), ChromaDB handles this comfortably. If performance degrades, IntentOS can optionally swap to a persistent Qdrant instance — but this should never be necessary for personal use.

---

## Privacy Guarantees

The RAG system holds more sensitive data than any other part of IntentOS — it has read, summarised, and embedded the content of the user's files. These guarantees are non-negotiable:

**All index data stays local.** Nothing in the RAG system is ever transmitted to any external service. Not file contents, not file paths, not embeddings, not task history.

**Embeddings are not reversible.** The vector embeddings stored in the index cannot be reversed to reconstruct file content. Even if the index files were stolen, the original content is not recoverable from embeddings alone.

**The user can inspect everything.** A built-in `intentos rag status` command shows what has been indexed, what hasn't, and the size of each index. The user can remove any file or folder from the index at any time.

**The user can delete everything.** `intentos rag clear` wipes all three indexes completely. The next task will rebuild from scratch.

**Excluded paths are respected permanently.** If the user excludes a folder, it is never indexed, never read, and never referenced in context — regardless of what's in it.

---

## RAG-Powered Features

### Vague reference resolution
*"That presentation I made for the client meeting"* → finds it from task history and file content even without knowing the filename.

### Cross-file context
*"Summarise all the invoices from this quarter"* → file index retrieves all invoice documents matching the time filter, passes them to document_agent for summarisation.

### Proactive suggestions
After completing a task, the system can surface related files: *"I found 3 other invoices from Ahmed while doing that — want me to do anything with them?"*

### Preference-aware defaults
*"Export this as usual"* → user profile says preferred export format is PDF → exports as PDF without asking.

### Temporal references
*"The file from last Tuesday"*, *"what I downloaded this morning"*, *"the photos from my trip last month"* → file index filters by modification/creation date.

---

## Implementation Stack

| Component | Technology | Why |
|---|---|---|
| Vector database | ChromaDB | Embedded, no server, Python-native |
| Embedding model | nomic-embed-text via Ollama | Local, fast, high quality |
| Filesystem watcher | watchdog (Python) | Cross-platform, battle-tested |
| Document parsing | pypdf, python-docx, openpyxl | Format coverage |
| Image captioning | moondream2 via Ollama (optional) | Local vision model for image indexing |
| Text chunking | LangChain text splitters | Semantic chunking logic |
| Profile store | JSON + pydantic | Simple, human-readable, inspectable |

---

## Rollout Strategy

RAG is not available on day one of IntentOS. It is introduced progressively so it never feels slow or intrusive.

```
Phase 1 (v0.1) — No RAG
  Intent Kernel works with explicit instructions only.
  User must always specify exact file paths or names.

Phase 2 (v0.2) — File Index only
  Filesystem indexed in background.
  Vague file references start working.
  "Find the invoice from Ahmed" works.

Phase 3 (v0.3) — Task Index added
  Task history indexed.
  "Same thing as last time" works.
  Replay and pattern detection enabled.

Phase 4 (v0.4) — User Profile added
  Preference learning active.
  Proactive suggestions enabled.
  Full contextual awareness operational.
```

---

*IntentOS RAG System — context that makes language actually work.*
