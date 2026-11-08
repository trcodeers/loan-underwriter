from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    document_type: str
    original_filename: str
    file_size: int
    created_at: datetime
    

class ChecklistItem(BaseModel):
    document_type: str
    label: str
    required: bool
    uploaded: bool
    document_count: int


class DocumentChecklistResponse(BaseModel):
    application_id: int
    ready_for_analysis: bool
    items: list[ChecklistItem]
    
    
    
    
    
    
class DocumentExtractionResponse(BaseModel):
    document_id: int
    application_id: int
    original_filename: str
    page_count: int
    has_extractable_text: bool
    extracted_text: str
    
    
        
    