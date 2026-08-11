from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    question: str = Field(min_length=4, max_length=500)
    include_pubmed: bool = False
    conversation_id: str | None = None


class Citation(BaseModel):
    label: str
    title: str
    source_type: str
    year: str
    url: str
    excerpt: str
    evidence_level: str


class AnswerResponse(BaseModel):
    answer_markdown: str
    citations: list[Citation]
    safety_note: str
    retrieval_note: str


class PubMedSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)
