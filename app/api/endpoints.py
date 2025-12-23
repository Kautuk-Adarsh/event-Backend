import time
import json
import traceback
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.rag_engine import RAGEngine
from app.utils.file_handler import save_temp_file, cleanup_uploads
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa
from io import BytesIO

router = APIRouter()
rag_engine = RAGEngine()

@router.post("/auto-fill")
async def auto_fill(
    files: list[UploadFile] = File(...),
    schema: str = Form(..., alias="schema"),
    event_name: str = Form(...)
):
    """
    Auto-fill form fields using RAG engine with FIXED location tracking.
    
    This implementation properly tracks field locations and updates the original
    data structure, fixing the issue where Historical Learnings and Agency 
    Deliverables were not being filled.
    """
    try:
        # 1. Save uploaded files and ingest into RAG
        temp_paths = [save_temp_file(f) for f in files]
        rag_engine.ingest_documents(temp_paths)
        data = json.loads(schema)

        total_fields = 0
        filled_fields = 0

        # 2. Process each section
        for section_idx, section in enumerate(data["sections"]):
            print(f"\n{'='*60}")
            print(f"📝 Processing Section: {section['sectionName']}")
            print(f"{'='*60}")
            # 3. Collect all fields AND track their exact locations
            fields_to_process = []
            field_locations = []  
            for group_idx, group in enumerate(section["inputFields"]):
                for field_idx, field in enumerate(group["fields"]):
                    # Generate prompt if missing
                    if not field.get("prompt"):
                        # Build prompt from helperText or field name
                        helper_text = field.get("helperText", [])
                        field_name = field.get("inputName") or group.get("fieldsHeading") or "Field"
                        
                        if helper_text:
                            # Use helperText to create extraction prompt
                            combined_text = " ".join(helper_text)
                            field["prompt"] = f"Extract information about '{field_name}' for event '{{event_name}}': {combined_text}"
                        else:
                            # Fallback: use field name as prompt
                            field["prompt"] = f"Extract information about '{field_name}' for event '{{event_name}}'"
                    
                    # Store the location for mapping back results
                    field_locations.append({
                        "section_idx": section_idx,
                        "group_idx": group_idx,
                        "field_idx": field_idx
                    })

                    # Prepare field for processing
                    field["temp_id_name"] = field.get("inputName") or group.get("fieldsHeading") or "Field"
                    field["prompt"] = field["prompt"].replace("{event_name}", event_name)
                    fields_to_process.append(field)

            if not fields_to_process:
                print(f"⚠️  No fields to process in {section['sectionName']}")
                continue

            total_fields += len(fields_to_process)
            print(f"🔍 Found {len(fields_to_process)} fields to auto-fill")

            try:
                # 4. Extract values using RAG engine
                extracted_values = rag_engine.query_batch(
                    section["sectionName"],
                    fields_to_process
                )

                print(f"\n📝 Mapping extracted values back to form...")
                for i, location in enumerate(field_locations):
                    field = fields_to_process[i]
                    val = extracted_values.get(str(i), "Nil")

                    # Get references to the actual field in the ORIGINAL data structure
                    section_ref = data["sections"][location["section_idx"]]
                    group_ref = section_ref["inputFields"][location["group_idx"]]
                    field_ref = group_ref["fields"][location["field_idx"]]

                    # Track success
                    if val and val != "Nil":
                        filled_fields += 1

                    # Handle different data types
                    data_type = field.get("dataType", "String")

                    if data_type == "Array":
                        if val and val != "Nil":
                            # Split by comma if multiple values
                            if isinstance(val, str) and "," in val:
                                field_ref["inputValue"] = [v.strip() for v in val.split(",")]
                            elif isinstance(val, list):
                                field_ref["inputValue"] = val
                            else:
                                field_ref["inputValue"] = [str(val)]
                        else:
                            field_ref["inputValue"] = []

                    elif data_type == "Object":
                        # Handle stakeholder objects: "Name (email@example.com)"
                        if val and val != "Nil" and isinstance(val, str) and "(" in val:
                            try:
                                name_part, email_part = val.split("(", 1)
                                field_ref["inputValue"] = {
                                    "Name": name_part.strip(),
                                    "Email": email_part.replace(")", "").strip()
                                }
                            except:
                                field_ref["inputValue"] = {
                                    "Name": str(val),
                                    "Email": "Nil"
                                }
                        elif val and val != "Nil" and isinstance(val, dict):
                            # Already an object
                            field_ref["inputValue"] = val
                        else:
                            field_ref["inputValue"] = {
                                "Name": val if val != "Nil" else "Nil",
                                "Email": "Nil"
                            }

                    else:
                        # String, Date, Number - assign directly
                        field_ref["inputValue"] = val

                    # Log individual field results
                    field_name = field.get("inputName", "Unknown")
                    status = "✓" if val and val != "Nil" else "✗"
                    display_val = str(val)[:60] if val else "Nil"
                    print(f"  {status} {field_name}: {display_val}")

            except Exception as e:
                print(f"❌ Error processing section {section['sectionName']}: {e}")
                traceback.print_exc()
                # Mark all fields as Nil on error
                for location in field_locations:
                    section_ref = data["sections"][location["section_idx"]]
                    group_ref = section_ref["inputFields"][location["group_idx"]]
                    field_ref = group_ref["fields"][location["field_idx"]]
                    field_ref["inputValue"] = "Nil"

            # Small delay between sections to avoid rate limiting
            time.sleep(1)

        # 6. Summary
        completion_rate = (filled_fields / total_fields * 100) if total_fields > 0 else 0
        print(f"\n{'='*60}")
        print(f"✅ Auto-fill Complete!")
        print(f"📊 Filled: {filled_fields}/{total_fields} fields ({completion_rate:.1f}%)")
        print(f"{'='*60}\n")

        cleanup_uploads()

        return {
            "data": data,
            "stats": {
                "total_fields": total_fields,
                "filled_fields": filled_fields,
                "completion_rate": completion_rate
            }
        }

    except Exception as e:
        cleanup_uploads()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    

# ----endpoint for the pdf downloader-----

@router.post("/generate-pdf")
async def generate_pdf(schema: str = Form(...)):
    try:
        data_json = json.loads(schema)
        
        # Prepare helper for top header
        top_data = {}
        for section in data_json["sections"]:
            for group in section["inputFields"]:
                for field in group["fields"]:
                    if field.get("inputName"):
                        top_data[field["inputName"]] = field.get("inputValue")

        # Load Template
        env = Environment(loader=FileSystemLoader("app/templates"))
        template = env.get_template("pdf_template.html")
        html_content = template.render(
            sections=data_json["sections"],
            data=top_data
        )

        # Convert HTML to PDF
        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)

        if pisa_status.err:
            raise HTTPException(status_code=500, detail="PDF Generation Error")

        pdf_buffer.seek(0)
        return Response(
            content=pdf_buffer.getvalue(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=Event_Brief.pdf"
            }
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))