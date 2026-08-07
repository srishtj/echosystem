import pytest
from pydantic import ValidationError

from extraction.schemas import Entity, Relation, ExtractionResult


def test_valid_entity():
    e = Entity(name="Acme Corp", type="Company")
    assert e.name == "Acme Corp"
    assert e.type == "Company"


def test_entity_rejects_invalid_type():
    with pytest.raises(ValidationError):
        Entity(name="Acme Corp", type="Nonprofit")


def test_valid_relation():
    r = Relation(
        source="Acme Corp",
        target="Widget Inc",
        relation_type="ACQUIRED",
        evidence="Acme announced the acquisition today.",
    )
    assert r.relation_type == "ACQUIRED"


def test_relation_rejects_invalid_relation_type():
    with pytest.raises(ValidationError):
        Relation(
            source="Acme Corp",
            target="Widget Inc",
            relation_type="MERGED_WITH",
            evidence="Not a valid relation type.",
        )


def test_relation_requires_evidence():
    with pytest.raises(ValidationError):
        Relation(source="A", target="B", relation_type="SUPPLIES")


def test_extraction_result_round_trip():
    result = ExtractionResult(
        entities=[Entity(name="Acme", type="Company")],
        relations=[
            Relation(
                source="Acme",
                target="Widget",
                relation_type="SUPPLIES",
                evidence="Acme supplies Widget with parts.",
            )
        ],
        summary="Acme supplies Widget with parts.",
    )
    dumped = result.model_dump()

    assert dumped["entities"][0]["name"] == "Acme"
    assert dumped["relations"][0]["relation_type"] == "SUPPLIES"
    assert dumped["summary"] == "Acme supplies Widget with parts."
