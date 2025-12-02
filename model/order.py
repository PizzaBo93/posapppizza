from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class Order(BaseModel):
    order_type: str
    table_number: Optional[int] = None
    note: Optional[str] = None
    items: Dict[str, int]
    total: int