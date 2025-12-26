import os
import json
import re
import time
from typing import List, Optional, Dict
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredPowerPointLoader,
    TextLoader,
    UnstructuredExcelLoader
)
from langchain_core.documents import Document

class RAGEngine:
    """
    JSON-optimized RAG Engine with dual-strategy:
    1. For JSON: Use full JSON context (it's already structured)
    2. For other files: Use vector search
    """

    def __init__(self):
        load_dotenv()

        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY not found in .env file")

        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

        self.llm = ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0,
            groq_api_key=groq_key,
            max_retries=3
        )

        self.vector_db = None
        self.context_cache = {}
        self.processed_files = []
        self.json_content = None  # Store full JSON if available

        print("✓ RAG Engine initialized with Groq (GPT-OSS 120B)")

    def ingest_documents(self, file_paths: List[str]):
        """Ingest multiple file types with JSON optimization"""
        all_docs = []
        self.processed_files = []
        self.json_content = None

        print(f"\n📂 Processing {len(file_paths)} file(s)...")
        print("=" * 60)

        for path in file_paths:
            filename = os.path.basename(path)
            ext = path.lower()

            try:
                # PDF Files
                if ext.endswith('.pdf'):
                    print(f"📄 Loading PDF: {filename}...", end=" ")
                    loader = PyPDFLoader(path)
                    docs = loader.load()
                    if docs and any(doc.page_content.strip() for doc in docs):
                        all_docs.extend(docs)
                        self.processed_files.append(filename)
                        print(f"✓ ({len(docs)} pages)")
                    else:
                        print("⚠ PDF appears to be scanned (no text found)")

                # Word Documents
                elif ext.endswith('.docx') or ext.endswith('.doc'):
                    print(f"📝 Loading Word: {filename}...", end=" ")
                    loader = Docx2txtLoader(path)
                    docs = loader.load()
                    all_docs.extend(docs)
                    self.processed_files.append(filename)
                    print(f"✓ ({len(docs)} sections)")

                # PowerPoint Presentations
                elif ext.endswith('.pptx') or ext.endswith('.ppt'):
                    print(f"📊 Loading PowerPoint: {filename}...", end=" ")
                    try:
                        loader = UnstructuredPowerPointLoader(path)
                        docs = loader.load()
                        all_docs.extend(docs)
                        self.processed_files.append(filename)
                        print(f"✓ ({len(docs)} slides)")
                    except Exception as ppt_error:
                        print(f"⚠ PowerPoint error: {str(ppt_error)[:50]}")

                # Text Files
                elif ext.endswith('.txt'):
                    print(f"📃 Loading Text: {filename}...", end=" ")
                    loader = TextLoader(path, encoding='utf-8')
                    docs = loader.load()
                    all_docs.extend(docs)
                    self.processed_files.append(filename)
                    print(f"✓")

                # JSON Files - SPECIAL HANDLING
                elif ext.endswith('.json'):
                    print(f"📖 Loading JSON: {filename}...", end=" ")
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)

                        # Store the full JSON for direct querying
                        self.json_content = json_data

                        # Also convert to text for vector search (as backup)
                        text_content = self._json_to_text(json_data)
                        doc = Document(
                            page_content=text_content,
                            metadata={"source": filename, "type": "json"}
                        )
                        all_docs.append(doc)
                        self.processed_files.append(filename)
                        print(f"✓ (JSON-optimized mode enabled)")
                    except Exception as json_error:
                        print(f"⚠ JSON error: {str(json_error)[:50]}")

                # Excel Files
                elif ext.endswith('.xlsx') or ext.endswith('.xls'):
                    print(f"📊 Loading Excel: {filename}...", end=" ")
                    try:
                        loader = UnstructuredExcelLoader(path, mode="elements")
                        docs = loader.load()
                        all_docs.extend(docs)
                        self.processed_files.append(filename)
                        print(f"✓ ({len(docs)} sheets)")
                    except Exception as excel_error:
                        print(f"⚠ Excel error: {str(excel_error)[:50]}")

                else:
                    print(f"⊘ Skipping unsupported file: {filename}")

            except Exception as e:
                print(f"✗ Error loading {filename}: {str(e)[:50]}")

        print("=" * 60)

        if not all_docs:
            print("⚠ WARNING: No documents were successfully loaded!")
            return

        # Create vector database
        print(f"📚 Splitting {len(all_docs)} document(s) into chunks...", end=" ")
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        docs = splitter.split_documents(all_docs)
        print(f"✓ Created {len(docs)} chunks")

        print(f"🔍 Creating vector database...", end=" ")
        if docs:
            self.vector_db = Chroma.from_documents(docs, self.embeddings)
            print(f"✓")
            print(f"\n✅ Successfully processed {len(self.processed_files)} file(s)")
            print(f"   Files: {', '.join(self.processed_files)}")
            print(f"   Total chunks indexed: {len(docs)}")
            if self.json_content:
                print(f"   🚀 JSON-optimized extraction enabled\n")
            else:
                print()

    def query_batch(self, section_name: str, fields: List[Dict]) -> Dict[str, str]:
        """
        Smart batch processing:
        - If JSON available: Use full JSON context (more accurate)
        - Otherwise: Use vector search
        """
        if not self.vector_db:
            print("⚠ No documents indexed")
            return {str(i): "Nil" for i in range(len(fields))}

        results = {}
        # Initialize results with Nil so we always return a full dictionary
        for i in range(len(fields)):
            results[str(i)] = "Nil"

        batch_size = 3
        total_batches = (len(fields) + batch_size - 1) // batch_size

        print(f"\n🤖 Extracting {len(fields)} fields in {total_batches} batches...")

        for i in range(0, len(fields), batch_size):
            batch = fields[i:i + batch_size]
            batch_num = i // batch_size + 1

            print(f"  Batch {batch_num}/{total_batches}...", end=" ")
            
            # Use a local try-except for the micro-batch
            try:
                batch_results = self._process_micro_batch(section_name, batch, i)
                results.update(batch_results)
                print("✓")
            except Exception as e:
                print(f"⚠ Micro-batch {i} failed: {e}. Skipping these fields.")
                # The fields in 'results' remain "Nil", but the rest of the section continues

            if i + batch_size < len(fields):
                time.sleep(0.5)

        # Calculate success rate
        filled = sum(1 for v in results.values() if v and v != "Nil")
        total = len(results)
        success_rate = (filled / total * 100) if total > 0 else 0

        print(f"✅ Extraction complete: {filled}/{total} fields filled ({success_rate:.1f}%)\n")

        return results

    def _process_micro_batch(self, section_name: str, fields: List[Dict], start_idx: int) -> Dict[str, str]:
        """Process a small batch of fields with localized error handling and defined prompts."""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Get context using optimal strategy
                if self.json_content:
                    # Strategy 1: Use full JSON (best for structured data)
                    context = self._get_json_context(section_name)
                else:
                    # Strategy 2: Use vector search (for unstructured docs)
                    context = self._get_smart_context(section_name, fields)

                context = self._sanitize_text(context)

                # Limit context length
                max_context_chars = 6000  # Increased for JSON
                if len(context) > max_context_chars:
                    half = max_context_chars // 2
                    context = context[:half] + "... [middle content omitted] ..." + context[-half:]

                # Create tasks using the start_idx to maintain unique IDs
                tasks = []
                for i, f in enumerate(fields):
                    # Safer fallback: check if helperText exists and has items
                    helper_text_list = f.get("helperText", [])
                    label = f.get("inputName")

                    if not label and len(helper_text_list) > 0:
                        label = helper_text_list[0]

                    if not label:
                        label = f.get("temp_id_name", "Narrative Summary")

                    tasks.append({
                        "id": str(start_idx + i),
                        "label": self._sanitize_text(label),
                        "task": self._sanitize_text(f.get("prompt", ""))
                    })

                system_prompt = f"""You are an expert event brief extractor for the '{section_name}' section.

TASK: Extract the EXACT requested information from the context.

CRITICAL RULES:
1. Return ONLY valid JSON. Keys MUST be the 'id' strings provided.
2. Search the ENTIRE context THOROUGHLY - information may be anywhere.
3. Extract EXACT values (names, numbers, dates, URLs) as they appear in the context.
4. For each task, look for ANY related information in the context - be flexible with terminology.
5. For stakeholders: use format "Name (email@example.com)". If email is missing, use "Name (Nil)".
6. Use "Nil" ONLY if information is truly absent after thorough search.
7. Match these common terms:
   - "name"/"title" → Project Name
   - "emb"/"event_code" → EMB
   - "budget"/"cost"/"total" → Budget
   - "country"/"location" → Country
   - "producer"/"lead"/"manager" → Producer
   - "executive_sponsor"/"fm"/"field_marketer" → Executive Sponsor
Example:
{{
  "0": "IBM Cloud Modernization Expo 2025",
  "1": "2025-11-20",
  "2": "Linda Hamilton (linda.h@ibm.com)"
}}

Return ONLY the JSON object with NO additional text."""

                user_prompt = f"""
CONTEXT FROM DOCUMENTS:
{context}

TASKS:
{json.dumps(tasks, indent=2)}

Return the extracted data as a JSON object:
"""

                # Execute LLM Call
                response = self.llm.invoke([
                    ("system", system_prompt),
                    ("human", user_prompt)
                ])

                # Safe JSON Parsing
                content = response.content.strip()
                try:
                    # Remove potential markdown formatting
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()

                    return json.loads(content)
                except json.JSONDecodeError:
                    print(f"⚠️ AI returned invalid JSON for a micro-batch. Result: {content[:100]}...")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    else:
                        raise ValueError("LLM response was not valid JSON")

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    print(f"(failed)", end=" ")
                    return {str(start_idx + i): "Nil" for i in range(len(fields))}

    def _get_json_context(self, section_name: str) -> str:
        """
        For JSON files: Return relevant section(s) of the JSON
        This is more accurate than vector search for structured data
        """
        if not self.json_content:
            return ""

        # Map section names to JSON keys - EXPANDED MAPPING
        section_key_map = {
            "project overview": ["project_kickoff", "basic_info", "event_details", "event","project"],
            "project stakeholders": ["contacts", "stakeholders", "team", "people"],
            "objectives & audience": ["objectives", "audience", "goals", "targets"],
            "story & client experience": ["story", "experience", "message", "narrative"],
            "historical learnings": ["historical_learnings", "historical_context", "previous_year", "history", "learnings"],
            "agency deliverables": ["agency_deliverables", "agency_requirements", "deliverables", "blue_studio", "must_haves"],
        }

        section_lower = section_name.lower()
        relevant_keys = []

        # Find matching keys
        for section_keyword, json_keys in section_key_map.items():
            if section_keyword in section_lower or any(k in section_lower for k in json_keys):
                relevant_keys.extend(json_keys)

        # Extract relevant sections
        relevant_data = {}
        for key in relevant_keys:
            if key in self.json_content:
                relevant_data[key] = self.json_content[key]

        # If nothing found, return full JSON (it's small enough)
        if not relevant_data or section_lower in ["project overview","project stakeholders"]:
            # For important sections, return FULL JSON to ensure no data is missed
            return self._json_to_text(self.json_content)

        # Return as formatted text (easier for LLM to read)
        return self._json_to_text(relevant_data)

    def _get_smart_context(self, section_name: str, fields: List[Dict]) -> str:
        """Vector search fallback for non-JSON files"""
        all_chunks = []
        seen_content = set()

        # Get chunks for section and fields
        queries = [section_name] + [f"{f.get('temp_id_name', '')} {f.get('prompt', '')}" for f in fields]

        for query in queries[:5]:  # Limit queries
            if query in self.context_cache:
                chunks = self.context_cache[query]
            else:
                chunks = self.vector_db.similarity_search(query, k=2)
                self.context_cache[query] = chunks

            for chunk in chunks:
                content = chunk.page_content
                if content not in seen_content and content.strip():
                    all_chunks.append(content)
                    seen_content.add(content)
                    if len(all_chunks) >= 6:
                        break

            if len(all_chunks) >= 6:
                break

        return "\n\n---\n\n".join(all_chunks)

    def _json_to_text(self, json_data, prefix: str = "") -> str:
        """Convert JSON to readable text"""
        lines = []

        if isinstance(json_data, dict):
            for key, value in json_data.items():
                readable_key = key.replace('_', ' ').replace('-', ' ').title()

                if isinstance(value, dict):
                    lines.append(f"{prefix}{readable_key}:")
                    for sub_key, sub_value in value.items():
                        sub_readable_key = sub_key.replace('_', ' ').replace('-', ' ').title()
                        lines.append(f"{prefix}  {sub_readable_key}: {sub_value}")
                elif isinstance(value, list):
                    lines.append(f"{prefix}{readable_key}: {', '.join(str(v) for v in value)}")
                else:
                    lines.append(f"{prefix}{readable_key}: {value}")

        elif isinstance(json_data, list):
            for i, item in enumerate(json_data, 1):
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}Item {i}:")
                    lines.append(self._json_to_text(item, prefix + "  "))
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            return str(json_data)

        return "\n".join(lines)

    def _sanitize_text(self, text: str) -> str:
        """Sanitize text to prevent API errors - LESS AGGRESSIVE"""
        if not text:
            return ""
        # Only fix problematic characters, don't truncate aggressively
        text = text.replace('\xa0', ' ').replace('\u2013', '-').replace('\u2014', '-')
        text = re.sub(r'[^\x00-\x7E]+', ' ', text)
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        text = text.replace('', '')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = ' '.join(text.split())

        if len(text) > 2000:
            text = text[:2000] + "..."

        return text

    def get_stats(self) -> Dict:
        """Get engine statistics"""
        return {
            "files_processed": len(self.processed_files),
            "files": self.processed_files,
            "json_mode": self.json_content is not None,
            "chunks_indexed": len(self.context_cache) if self.vector_db else 0,
            "vector_db_ready": self.vector_db is not None
        }
