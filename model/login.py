from typing import Optional, List, Dict, Any
from pydantic import BaseModel

class Login(BaseModel):
    username: str
    password: str