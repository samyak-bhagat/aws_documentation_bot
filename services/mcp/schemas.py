from pydantic import BaseModel


class SearchResult(BaseModel):
    title: str
    url: str
    excerpt: str | None = None


class DocumentContent(BaseModel):
    url: str
    title: str
    content: str
    sections: list[str] = []


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class ReadRequest(BaseModel):
    url: str
