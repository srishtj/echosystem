from dotenv import load_dotenv
import os
load_dotenv()

import instructor
from groq import Groq
from extraction.schemas import ExtractionResult
from ingestion.celery_app import celery_app

client = instructor.from_groq(
    Groq(api_key=os.environ["GROQ_API_KEY"]),
    mode=instructor.Mode.JSON
)

@celery_app.task
def extract_entities(title: str, text: str):
    result: ExtractionResult = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_model=ExtractionResult,
        max_retries=2,
        messages=[{
            "role": "user",
            "content": (
                "Extract entities and relations from this article."
                f"\n\nTitle: {title}\n\nText: {text}"
            ),
        }],
    )
    
    print(result.model_dump())
    return result.model_dump()