### 2. Backend README
**File Location:** `event-backend/README.md`

```markdown
# ⚙️ RAG Intelligence Engine (Backend)

The "Brain" of the Event Automation system. A production-ready **FastAPI** application utilizing **Retrieval-Augmented Generation (RAG)** to structure unstructured data.

## 🚀 Overview
This backend handles the heavy lifting: document ingestion, vectorization, contextual retrieval, and high-fidelity PDF generation. It uses **Llama 3.3** via Groq for sub-second data extraction.

## 🛠️ Tech Stack
- **Framework:** FastAPI (Python 3.10+)
- **Orchestration:** LangChain
- **LLM:** Groq (Llama 3.3-70b-versatile)
- **Vector DB:** ChromaDB (Persistent Storage)
- **Embeddings:** Local HuggingFace (`all-MiniLM-L6-v2`) to bypass rate limits.
- **PDF Engine:** Jinja2 + xhtml2pdf

## ✨ Key Features
- **Multi-Format Loader:** Built-in support for `.pdf`, `.docx`, `.pptx`, and `.json`.
- **Intelligent Batching:** Processes extraction tasks in optimized sections to respect LLM rate limits (RPM/TPM).
- **Unicode Sanitization:** A custom regex-based pipeline that cleans AI-generated text to prevent "black square" rendering bugs in PDF exports.
- **Persistent Knowledge Base:** ChromaDB implementation that saves indexed documents to disk, preventing redundant processing.

## 📦 Installation & Setup
1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate # Windows: .\venv\Scripts\activate

## Install dependencies:
    pip install -r requirements.txt
## Configure your .env file:
    GROQ_API_KEY=your_key_here
## Run the server:
    uvicorn app.main:app --reload

🔌 API Endpoints
- **POST /auto-fill: Accepts documents and schema; returns AI-filled JSON.**
- **POST /generate-pdf: Accepts JSON; returns a branded, sanitized PDF file.**