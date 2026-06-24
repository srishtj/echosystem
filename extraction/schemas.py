from pydantic import BaseModel, Field
from typing import Literal

class Entity(BaseModel):
    name: str
    type: Literal["Company", "Person", "Material", "Product"]

class Relation(BaseModel):
    source: str
    target: str
    relation_type: Literal[
        "COMPETES_WITH", "INVESTS_IN", "THREATENED_BY", "PARTNERS_WITH", "ACQUIRED", "SUPPLIES"
    ]
    evidence: str = Field(..., description="Direct quote/paraphrase supporting this")

class ExtractionResult(BaseModel):
    entities: list[Entity]
    relations: list[Relation]
    summary: str

