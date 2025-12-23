from pydantic import BaseModel
from typing import List, Optional, Any

class FormField(BaseModel):
    inputName: str
    inputValue: Optional[Any] = None
    dataType: str
    fieldType: str
    options: Optional[List[str]] = None
    prompt: Optional[str] = None

class FieldGroup(BaseModel):
    fieldsHeading: str
    fields: List[FormField]

class Section(BaseModel):
    sectionName: str
    inputFields: List[FieldGroup]

class EventSchema(BaseModel):
    templateName: str
    sections: List[Section]