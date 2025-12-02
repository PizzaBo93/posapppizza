from typing import Optional, List, Dict, Any

from pydantic import BaseModel

class User(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    store_code: Optional[str]
    role: str
    permissions: Dict[str, bool]