from datetime import datetime, timezone
import re
from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Item
from app.schemas import AskRequest, AskResponse, CitationItem, ErrorResponse
from app.services.llm_router import answer_question
from app.services.retrieval import retrieve_items

router = APIRouter(prefix="/ask", tags=["ask"])


GREETING_REGEX = re.compile(
    r"^\s*(hi|hello|hey|greetings|howdy|good\s+(morning|afternoon|evening)|who\s+are\s+you|what\s+can\s+you\s+do|help)\b[\s!\.\?]*$",
    re.IGNORECASE,
)


@router.post(
    "",
    response_model=AskResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Ask competitive intelligence questions grounded strictly in retrieved items",
)
def ask_analyst(request: AskRequest, db: Session = Depends(get_db)):
    """
    Retrieves top 12 items via keyword + tag + competitor filtering over SQLite (no vector DB),
    sends strictly those items to gemini-2.5-flash to produce a grounded answer citing item IDs,
    or replies 'No evidence found' if unsupported.
    """
    # 0. Gracefully handle conversational greetings and capability questions
    if GREETING_REGEX.match(request.question):
        return AskResponse(
            question=request.question,
            answer=(
                "Hello! I am Meridian, your AI competitive intelligence analyst for US commercial insurance brokerages.\n\n"
                "I track verified market disclosures across 6 major brokers (Marsh McLennan, Aon, WTW, Arthur J. Gallagher, Brown & Brown, and Hub International). You can ask me about:\n"
                "• M&A Deals & Regional Rollups (e.g., \"What M&A deals did Marsh McLennan complete?\")\n"
                "• Executive Leadership Restructuring (e.g., \"Who was appointed at Aon or Gallagher?\")\n"
                "• Digital Product & Risk Modeling Tools (e.g., \"What cyber risk tools were launched?\")\n"
                "• Commercial Rate & Pricing Surveys (e.g., \"What are the latest property rate trends?\")\n\n"
                "Feel free to click one of the suggested questions above or type a query about any competitor."
            ),
            citations=[],
            model_used="meridian-analyst-intro",
            retrieved_count=0,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # 1. Retrieve top 12 items from SQLite
    retrieved_items = retrieve_items(
        db=db,
        query=request.question,
        competitor_id=request.competitor_id,
        tag=request.tag,
        top_k=12,
    )


    # 2. Call LLM Router
    llm_result = answer_question(query=request.question, items=retrieved_items)
    answer_text = llm_result["answer"]
    reported_citations = set(llm_result.get("cited_item_ids", []))

    # Also detect inline [cite:item_id] patterns if LLM outputted them in text
    inline_citations = re.findall(r"\[cite:([a-zA-Z0-9_\-]+)\]", answer_text)
    for c_id in inline_citations:
        reported_citations.add(c_id)

    # 3. Build CitationItem models for all cited items that were retrieved
    item_map: Dict[str, Item] = {item.id: item for item in retrieved_items}
    citations: List[CitationItem] = []

    for cite_id in reported_citations:
        if cite_id in item_map:
            item = item_map[cite_id]
            comp_name = item.competitor.name if hasattr(item, "competitor") and item.competitor else item.competitor_id
            citations.append(
                CitationItem(
                    id=item.id,
                    competitor_id=item.competitor_id,
                    competitor_name=comp_name,
                    title=item.title,
                    tag=item.tag,
                    date=item.date,
                    summary=item.summary,
                    source_url=item.source_url,
                )
            )

    return AskResponse(
        question=request.question,
        answer=answer_text,
        citations=citations,
        model_used=llm_result["model_used"],
        retrieved_count=len(retrieved_items),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
