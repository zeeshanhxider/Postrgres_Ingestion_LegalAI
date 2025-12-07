# Legal Case Ingestion Pipeline

Production-grade pipeline for extracting structured data from Washington State court opinion PDFs and populating a PostgreSQL database with full RAG (Retrieval-Augmented Generation) support.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PDF Input                                       │
│                    (Court opinions from downloads/)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PDFExtractor                                       │
│              LlamaParse API (primary) + pdfplumber (fallback)               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLMExtractor                                       │
│                    Ollama qwen:32b structured extraction                     │
│     Extracts: parties, judges, attorneys, citations, statutes, issues       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CaseProcessor                                       │
│              Orchestrates PDF → LLM → ExtractedCase model                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DatabaseInserter                                     │
│                   Inserts case + related entities                            │
│            Uses DimensionService for FK resolution                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RAGProcessor                                        │
│                                                                              │
│  ┌──────────────┐  ┌───────────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   Chunker    │  │ SentenceProcessor │  │WordProcessor │  │  Phrase    │ │
│  │ (350 words)  │→ │ (citation-aware)  │→ │ (dictionary) │  │ Extractor  │ │
│  └──────────────┘  └───────────────────┘  └──────────────┘  └────────────┘ │
│                                                                              │
│  Configurable: chunk_embedding_mode, phrase_filter_mode                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL + pgvector                                │
│                                                                              │
│  cases ─┬─► parties        case_chunks ─► case_sentences ─► word_occurrence │
│         ├─► case_judges    case_phrases   word_dictionary                   │
│         ├─► attorneys      embeddings (1024-dim vectors)                    │
│         ├─► citation_edges                                                  │
│         ├─► statute_citations                                               │
│         └─► issues_decisions                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

| File                    | Purpose                                              |
| ----------------------- | ---------------------------------------------------- |
| `config.py`             | Environment configuration (DB, Ollama, LlamaParse)   |
| `models.py`             | Data models: `ExtractedCase`, `Party`, `Judge`, etc. |
| `pdf_extractor.py`      | PDF to text using LlamaParse + pdfplumber fallback   |
| `llm_extractor.py`      | Structured extraction using Ollama LLM               |
| `case_processor.py`     | Orchestrates extraction pipeline                     |
| `db_inserter.py`        | Database insertion with RAG integration              |
| `dimension_service.py`  | FK resolution for dimension tables                   |
| `chunker.py`            | Section-aware text chunking                          |
| `sentence_processor.py` | Sentence extraction with citation protection         |
| `word_processor.py`     | Word dictionary and occurrence tracking              |
| `phrase_extractor.py`   | Legal phrase n-gram extraction                       |
| `rag_processor.py`      | Main RAG orchestrator                                |

## Usage

### Process a Single Case

```bash
python run_pipeline.py downloads/Supreme_Court_Opinions/2025/January/case.pdf \
    --metadata downloads/Supreme_Court_Opinions/metadata.csv
```

### Batch Processing

```bash
python run_pipeline.py downloads/Supreme_Court_Opinions/2025/ \
    --metadata downloads/Supreme_Court_Opinions/metadata.csv \
    --limit 50
```

### RAG Options

```bash
# Chunk embedding modes
--chunk-embedding all        # Embed all chunks (default)
--chunk-embedding important  # Only ANALYSIS, FACTS, HOLDING sections
--chunk-embedding none       # Skip chunk embeddings

# Phrase filtering modes
--phrase-filter strict       # Only legal terminology (default)
--phrase-filter relaxed      # All meaningful phrases

# Skip RAG entirely
--no-rag
```

### Verify a Case

```bash
python -m pipeline.run_pipeline --verify --case-id 21
```

### Extract Only (No Database)

```bash
python run_pipeline.py case.pdf --no-db
```

## Environment Variables

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5435/cases_llama3_3

# Ollama LLM
OLLAMA_BASE_URL=https://ollama.legaldb.ai
OLLAMA_MODEL=qwen:32b
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large

# LlamaParse (PDF OCR)
LLAMA_CLOUD_API_KEY=llx-...
```

## Database Tables Populated

**Core Tables:**

- `cases` - Main case record with full text and embedding
- `parties` - Plaintiff, defendant, appellant, respondent
- `case_judges` - Judges linked via `judges` table
- `attorneys` - Legal representation
- `citation_edges` - Case citations
- `statute_citations` - Statutory references
- `issues_decisions` - Legal issues and outcomes

**RAG Tables:**

- `case_chunks` - Text chunks with section type and optional embedding
- `case_sentences` - Sentences within chunks
- `word_dictionary` - Unique words across corpus
- `word_occurrence` - Word positions in sentences
- `case_phrases` - Extracted legal phrases (2-4 grams)

**Dimension Tables:**

- `courts_dim` - Court information (resolved to `court_id`)
- `case_types` - Case type taxonomy
- `stage_types` - Procedural stage taxonomy

## Example Output

```
Processing: 102586-6.pdf
  Metadata: 102,586-6 - Pub. Util. Dist. No. 1 v. State
  Extracted 28547 chars from 12 pages
  Running LLM extraction...
  Extraction complete: 4 parties, 10 judges, 3 issues
✓ Inserted as case_id: 21
  RAG: 15 chunks, 142 sentences, 2847 words, 89 phrases
```
